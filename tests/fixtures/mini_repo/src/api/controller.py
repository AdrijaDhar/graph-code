from src.utils import parse_config


class BaseController:
    pass


class ApiController(BaseController):
    def handle_request(self, payload: str) -> dict:
        cfg = parse_config(payload)
        return {"ok": True, "cfg": cfg}
