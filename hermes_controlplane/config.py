from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    hermes_home: Path = Path.home() / ".hermes"
    controlplane_host: str = "127.0.0.1"
    controlplane_port: int = 8780
    controlplane_log_level: str = "info"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    @property
    def profiles_dir(self) -> Path:
        return self.hermes_home / "profiles"

    @property
    def global_state_db(self) -> Path:
        return self.hermes_home / "state.db"


settings = Settings()
