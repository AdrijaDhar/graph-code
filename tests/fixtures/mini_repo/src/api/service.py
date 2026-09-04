from src.utils import parse_config, unused_helper


class Service:
    def run(self, raw: str) -> int:
        cfg = parse_config(raw)
        return unused_helper() if cfg else 0
