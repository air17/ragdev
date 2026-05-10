from bleach import clean

from agent_tools.llms import query_deepseek


def markdown_to_telegram_html_ai(md_text):
    """Convert Markdown text to Telegram-compatible HTML using AI model."""
    system_prompt = (
        "You are a Markdown to HTML converter, that takes markdown input from user and returns valid HTML\n"
        "Here are the conversion rules you must follow:\n"
        "Use only the following HTML tags: <b>, <i>, <a>, <code>, <pre>, <s>, <u>, <em>, <strong> and <blockquote>.\n"
        "For markdown headers, wrap the text in <b> tags and add two newlines before and after as h1-6 tags not supported.\n"
        "Never ever use any tag other than the supported ones. If you want to use <br>, use \\n instead.\n"
        "For inline code, use <code> tags. For code blocks, use <pre> tags.\n"
        "For list items, just prepend each item with a bullet • and don't use unsupported list tags.\n"
        "All <, > and & symbols that are not a part of a tag or an HTML entity must be replaced with the corresponding HTML entities (< with &lt;, > with &gt; and & with &amp;).\n"
        "But never escape apostrophes (') with &apos; leave them as is as they are not part of HTML tags. Never use &apos; in output.\n"
        "Remove any unsupported tags and convert them to plain text.\n"
        "Ensure that 'a' tags have just a 'href' attribute.\n"
        "Add two newlines before and after blockquotes for spacing.\n"
        "In your final output should be valid HTML with only supported tags.\n"
        "If markdown input has no formatting, just return the plain text as is.\n"
        "If markdown input has syntax errors, like unclosed tags, try to fix them in the HTML output.\n"
        "Never change the text content, only convert the formatting. Don't try to fix the content even if it seems broken.\n"
        "Don't include any extra text or explanations in your response!\n\n"
        "Markdown Input:"
    )
    return remove_non_telegram_html(
        query_deepseek(
            md_text, model="deepseek-v4-flash", system_prompt=system_prompt
        ).strip()
    )


def remove_non_telegram_html(text: str) -> str:
    """
    Removes HTML tags and attributes that are not supported by Telegram from the given text.

    Args:
        text (str): The input text containing HTML.

    Returns:
        str: The cleaned text with unsupported HTML tags and attributes removed.
    """
    allowed_tags = {
        "a",
        "b",
        "strong",
        "i",
        "em",
        "u",
        "ins",
        "s",
        "strike",
        "del",
        "tg-spoiler",
        "code",
        "pre",
    }
    allowed_tag_attributes = {"a": ["href"]}
    allowed_protocols = {"http", "https", "tg"}
    return clean(
        text,
        tags=allowed_tags,
        attributes=allowed_tag_attributes,
        protocols=allowed_protocols,
        strip=True,
    )
