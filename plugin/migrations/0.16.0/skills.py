"""0.16.0 user skills: the data folder's old name, .workflow-manager-data/, becomes .delegate-data/.
convert(name, text) returns the new text, or the same text when there is nothing to do (safe to run twice)."""


def convert(name, text):
    return text.replace(".workflow-manager-data/", ".delegate-data/")
