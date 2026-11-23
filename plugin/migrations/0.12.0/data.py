"""0.12.0 machine data: nothing moves. The plugin now ships only the engine and one demo workflow; the workflows,
connections and shared processes it used to carry came from its author's own setup and are gone from it.
This step notes which of them this folder ran (from its done list), so the log says why they no longer run here:
their runs stay on the board, and a folder that wants one keeps it as a skill of its own. The plugin's category list
now holds only its own areas; any area this folder's own skills are named with that left it is written to the
folder's own list (config/categories.md), so their names stay valid."""
import json
import os
import re

REMOVED = {
    "shared-news-bbc-website", "connection-gmail", "connection-notion", "connection-outlook", "connection-slack",
    "connection-x", "workflow-ai-sota-model-alert", "workflow-finance-revolut-approval",
    "workflow-monitoring-airtable-uptime-email", "workflow-new-x-meeting-reply", "workflow-news-bbc-article",
    "workflow-news-bbc-manchester-alert", "workflow-news-butterfly-dashboard", "workflow-news-techcrunch-spain-startups",
    "workflow-property-bid-deadline-notion", "workflow-property-broker-alert", "workflow-property-for-sale-alert",
    "workflow-property-location-alert", "workflow-security-alert", "workflow-seo-local-rank-feasibility",
}


# the areas the plugin's list had before 0.12.0 and no longer has: (meaning)
MOVED_CATEGORIES = {'support': 'customer service: requests, changes to customer details, complaints, refunds',
    'kyc': 'know-your-customer and know-your-business: identity, company and owner checks, screening',
    'security': 'security alerts and account safety',
    'seo': 'local search and Google Maps ranking: where a business ranks and how high it could get',
    'finance': 'money and accounts: payments, approvals, invoices and banking alerts',
    'property': 'property: listings and sale or letting alerts',
    'ai': 'Keeping up with new AI models and how they compare',
    'monitoring': 'uptime and service status of the tools you use'}


def migrate(ctx):
    used = set()
    done = ctx.get("done_list")
    if done and os.path.isfile(done):
        with open(done, encoding="utf-8") as fh:
            for line in fh:
                try:
                    sk = json.loads(line).get("skill")
                except ValueError:
                    continue
                if sk in REMOVED:
                    used.add(sk)
    own = os.path.join(os.path.dirname(ctx["home"]), ".claude", "skills") if ctx.get("home") else ""
    gone = sorted(s for s in used if not os.path.isdir(os.path.join(own, s)))
    changes = []
    if gone:
        changes.append("no longer in the plugin, so they don't run here any more (their runs stay on the board): "
                       + ", ".join(gone))
    cats = categories(ctx, own)
    if cats:
        changes.append("this folder's own areas, which left the plugin's category list, now in config/categories.md: "
                       + ", ".join(cats))
    return changes


def categories(ctx, own):
    """Write the areas this folder's own skills are named with, that the plugin's list no longer has, to the
    folder's own list. Lines already there are kept; twice = no change."""
    names = os.listdir(own) if own and os.path.isdir(own) else []
    want = sorted({m.group(1) for n in names for m in [re.match(r"^(?:workflow|shared|trigger)-([a-z0-9]+)-", n)]
                   if m and m.group(1) in MOVED_CATEGORIES})
    if not want or not ctx.get("config"):
        return []
    path = os.path.join(ctx["config"], "categories.md")
    text = open(path, encoding="utf-8").read() if os.path.isfile(path) else (
        "# Categories (this folder's own)\n\nThe areas of this folder's own workflows, read together with the "
        "plugin's list (rule 10).\n\n| Category | What belongs here |\n|---|---|\n")
    add = [c for c in want if f"| `{c}` |" not in text]
    if not add:
        return []
    text = text.rstrip("\n") + "\n" + "".join(f"| `{c}` | {MOVED_CATEGORIES[c]} |\n" for c in add)
    os.makedirs(ctx["config"], exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return add
