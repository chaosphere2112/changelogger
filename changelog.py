import init, gh, sys
from args import milestone, since, unlabeled

repo = gh.GithubModel("/repos/UV-CDAT/uvcdat")

milestones = repo["milestones"]

found = False
milestones_to_exclude = []
for m in milestones:
	if m["title"] == str(milestone):
		found = True
	else:
		milestones_to_exclude.append(m["title"])

if found is False:
	print "Unable to find milestone %s" % milestone
	sys.exit(1)

# Assemble issues query

# We only care about closed issues
query = { "state": "closed" }

# Filter since whatever date was provided
if since is not None:
	query["since"] = "%d-%02d-%02dT00:00:00GMT" % (since.year, since.month, since.day)

# We may want to grab unlabeled issues as well, if they're since a date
if unlabeled is False:
	query["milestone"] = milestone

from urllib import urlencode
query = urlencode(query)

labels = repo["labels"]

# Used to sort open issues and stick at end of log
severity = ["High", "Critical"]

# Used to split category closed issues
kind = ["Enhancement", "Bug"]
# Used to categorize issues
category = []

# Ignored
irrelevant = ["Other", "Duplicate", "Invalid", "Question", "Gatekeeper", "wontfix", "unconfirmed"]

for label in labels:
	if label["name"] in severity or label["name"] in kind or label["name"] in irrelevant:
		continue
	category.append(label["name"])

def after_since(date):
	if since is None:
		return True
	date = date.split("T")[0]
	year, month, day = [int(p) for p in date.split("-")]
	if year < since.year:
		return False
	if year == since.year and month < since.month:
		return False
	if year == since.year and month == since.month and day < since.day:
		return False
	return True

issues = gh.GithubModel("/repos/UV-CDAT/uvcdat/issues?%s" % query)

issues_by_number = {}
for issue in issues:
	closed_date = issue["closed_at"]
	if closed_date is None:
		continue
	if not after_since(closed_date):
		continue
	if "milestone" not in issue or issue["milestone"] is None:
		if not after_since(issue["created_at"]):
			# This is an older issue... we should check on the comments to see if it was just closed recently,
			# but actually solved a while back
			if issue["comments"] != 0:
				for c in issue["comments"]:
					if after_since(c["created_at"]):
						# There was a comment after "since"
						break
				else:
					continue
		issues_by_number[str(issue["number"])] = issue
	elif issue["milestone"]["title"] not in milestones_to_exclude:
		issues_by_number[str(issue["number"])] = issue

pull_requests = [n for n, issue in issues_by_number.iteritems() if "pull_request" in issue]
issues = [n for n, issue in issues_by_number.iteritems() if "pull_request" not in issue]

issues_sorted = {}
issues_kinds = {}

for n in issues:
	issue = issues_by_number[n]
	issue_labels = issue["labels"]
	categorized = False
	for label in issue_labels:
		# Skip useless labels
		if label["name"] in irrelevant:
			break
	else:
		for label in issue_labels:
			# Prevent multiple occurences for issues
			if label["name"] in category and categorized is False:
				categorized = True
				if label["name"] not in issues_sorted:
					issues_sorted[label["name"]] = []
				issues_sorted[label['name']].append(n)
			if label["name"] in kind:
				issues_kinds[n] = label["name"]
		if n not in issues_kinds:
			issues_kinds[n] = ""

prs_for_issue = {}
import re
number_re = re.compile("\d+")
orphan_pr = []

for n in pull_requests:
	pr = issues_by_number[n]
	p = gh.GithubModel(pr["pull_request"]["url"])
	if p["merged"] is False:
		continue

	# Make sure it was merged after the since date, if that's provided
	if not after_since(p["merged_at"]):
		continue

	associated = False

	numbers = number_re.findall(pr["title"])
	numbers.extend(number_re.findall(pr["body"]))

	for num in numbers:
		if num in issues:
			if num not in prs_for_issue:
				prs_for_issue[num] = []
			if n not in prs_for_issue[num]:
				prs_for_issue[num].append(n)
			associated = True

	if associated is False:
		orphan_pr.append(n)

print "## Closed Issues"

categories = sorted(issues_sorted.keys())
for cat in categories:
	print "### {category}".format(category=cat)
	print ""
	# Sort the issues by bug vs enhancement
	cat_issues = issues_sorted[cat]
	sorted_issues = sorted(cat_issues, key=lambda n: issues_kinds[n])
	for n in sorted_issues:
		issue = issues_by_number[n]
		values = {
			"bug_or_enh": issues_kinds[n] if n in issues_kinds else "",
			"title": issue["title"],
			"url": issue["html_url"],
		}
		if n in prs_for_issue:
			links = ", ".join(["[#{num}]({url})".format(num=issues_by_number[a]["number"], url=issues_by_number[a]["html_url"]) for a in prs_for_issue[n]])
			values["links"] = links
			message = " * **{bug_or_enh}**: [{title}]({url}) ({links})".format(**values).encode("ascii", "xmlcharrefreplace")
		else:
			message = " * **{bug_or_enh}**: [{title}]({url})".format(**values).encode("ascii", "xmlcharrefreplace")

		print message
	print ""

print "## Merged Pull Requests\n"
orphan_pr.sort(key=lambda n: int(n))
for pr in orphan_pr:
	pr = issues_by_number[pr]
	values = {
		"number": pr["number"],
		"title": pr["title"],
		"url": pr["html_url"],
	}
	print " * [#{number}: {title}]({url})".format(**values).encode("ascii", "xmlcharrefreplace")

print ""


print "## Known Bugs\n"

open_bugs = gh.GithubModel("/repos/UV-CDAT/uvcdat/issues?state=open&labels=Bug")

critical_issues = []
high_issues = []
other = []

# Filter out unimportant/Categorize by severity
for bug in open_bugs:
	for label in bug["labels"]:
		if label["name"] in irrelevant:
			break
	else:
		for label in bug["labels"]:
			if label["name"] == "High":
				high_issues.append(bug)
				break
			elif label["name"] == "Critical":
				critical_issues.append(bug)
				break
		else:
			if "milestone" not in bug or bug["milestone"] is None:
				continue
			other.append(bug)


if len(critical_issues) > 0:
	print "### Critical\n"
	for issue in critical_issues:
		print " * [{title}]({url})".format(title=issue["title"].encode("ascii", "xmlcharrefreplace"), url=issue["html_url"].encode("ascii", "xmlcharrefreplace")).encode("ascii", "xmlcharrefreplace")
	print ""

if len(high_issues) > 0:
	print "### High Priority\n"
	for issue in high_issues:
		print " * [{title}]({url})".format(title=issue["title"].encode("ascii", "xmlcharrefreplace"), url=issue["html_url"].encode("ascii", "xmlcharrefreplace")).encode("ascii", "xmlcharrefreplace")
	print ""

if len(other) > 0:
	print "### Other\n"
	for issue in other:
		print " * [{title}]({url})".format(title=issue["title"].encode("ascii", "xmlcharrefreplace"), url=issue["html_url"].encode("ascii", "xmlcharrefreplace")).encode("ascii", "xmlcharrefreplace")
	print ""

if len(high_issues) == 0 and len(critical_issues) == 0 and len(other) == 0:
	print "No known issues!"