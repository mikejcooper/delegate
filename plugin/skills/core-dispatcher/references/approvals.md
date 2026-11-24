# Front door: A step that asks for the user's yes

Part of core-dispatcher (its SKILL.md says when to read this). Names in bold are sections of SKILL.md or of the
other files in this folder.

## Approvals
In every real run (started in the chat, by a schedule or from the Inbox), a workflow step that asks the user for a
yes (a "Send it?" before a send, post, payment, form or deletion) is **never asked in the chat**, whatever the step's
own wording says. What happens instead depends on the **Approve automatically** switch (`item_id.py setting`,
`auto_approve`; on unless the user turned it off), read once at the start of the request:

**On: answered yes.** Log the step with `run_item.py line`: `{"type":"Approved Automatically","step":"<the step's
title>","status":"done","result":"Approved automatically: <what it does, a few words>","ask":{"q":"<the question>",
"show":{<what it does: to, subject, a one-line gist, the attachment's file name>}},"because":"Approve automatically
is on"}`, then run the steps after it (the send itself, through its connection) as if the user said yes. The end
line's `done` lists what was sent. A test or a try as a test never sends, whatever the switch says (**A new workflow's runs**,
**Tests**).

**Off: waits on the Inbox.** The chat never stops for it; the run waits on the Inbox instead:
1. Log the step with `run_item.py line`: `{"type":"Asked You","step":"<the step's title>","status":"needs_user",
   "result":"Waiting for your yes on the Inbox","ask":{"q":"<the question, e.g. Send this email?>","show":{<what it
   would do: to, subject, a one-line gist, the attachment's file name; never a password or a full email body>},
   "yes":"<what yes does, 2-4 words: Send it>","no":"<what no does: Don't send>"},"io":{"out":{<everything the next
   step needs to carry on: recipient, subject, body, file paths>}}}`. `io.out` is what an answer picks up from, so it
   holds the finished message, not just its heading.
2. End the run `--status needs_user` with `"attention":"action"`, `waiting` "You: yes or no to <the action>" and
   `next` "answer it on the Inbox", and `--path` the path it would take on yes.
3. Go on with the next item. At the end of the request, say in one line how many runs wait on the Inbox.
A try as a test (a new workflow's run) never parks or sends anything: it logs the message as "would send", as before.
A try for real follows this section like any real run.
