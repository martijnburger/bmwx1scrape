from . import autoscout24, autotrack, gaspedaal, marktplaats, viabovag

SOURCES = {
    "marktplaats": marktplaats,
    "viabovag": viabovag,
    "autotrack": autotrack,
    "gaspedaal": gaspedaal,
    "autoscout24": autoscout24,
}

# AutoScout24 sluit in robots.txt AI-crawlers uit (GPTBot, ClaudeBot, ...). Deze scraper is daar
# geen van, maar de site doet alleen mee als je er zelf expliciet om vraagt: --sites autoscout24
DEFAULT_SITES = ["marktplaats", "viabovag", "autotrack", "gaspedaal"]
