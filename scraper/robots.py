"""robots.txt-parser met ondersteuning voor * en $ (urllib.robotparser kent die niet)."""
from __future__ import annotations

import re


class RobotRules:
    def __init__(self, text: str, agent: str):
        self.rules = self._select_rules(text, agent.lower())

    @staticmethod
    def _select_rules(text: str, agent: str) -> list[tuple[bool, str, re.Pattern]]:
        groups: list[tuple[list[str], list[tuple[str, str]]]] = []
        collecting_agents = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not collecting_agents:
                    groups.append(([], []))
                    collecting_agents = True
                groups[-1][0].append(value.lower())
            elif key in ("allow", "disallow") and groups:
                collecting_agents = False
                if value:
                    groups[-1][1].append((key, value))
            else:
                collecting_agents = False

        specific = [g for g in groups if any(a != "*" and agent.startswith(a) for a in g[0])]
        wildcard = [g for g in groups if "*" in g[0]]
        chosen = specific or wildcard
        rules = []
        for _, entries in chosen:
            for kind, pattern in entries:
                regex = re.escape(pattern).replace(r"\*", ".*")
                if regex.endswith(r"\$"):
                    regex = regex[:-2] + "$"
                rules.append((kind == "allow", pattern, re.compile(regex)))
        return rules

    def allowed(self, path_and_query: str) -> bool:
        """Langste overeenkomende regel wint; bij gelijke lengte wint Allow."""
        best_len, best_allow = -1, True
        for allow, pattern, regex in self.rules:
            if regex.match(path_and_query):
                length = len(pattern)
                if length > best_len or (length == best_len and allow):
                    best_len, best_allow = length, allow
        return best_allow
