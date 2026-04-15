from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str
    REFRESH_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    TMDB_API_KEY: str
    DATABASE_URL: str = "sqlite:///./movie_recommender.db"
    ENVIRONMENT: str = "development"  # "production" în prod — activează secure cookies + HSTS

    # Origini permise pentru CORS — în producție setează domeniul real (ex: "https://yourapp.com")
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # IP-urile proxy-urilor de încredere (Nginx, Cloudflare edge, AWS ALB etc.)
    # Separate prin virgulă. Dacă e gol → rate limiting pe IP direct (fără XFF).
    # Exemplu: TRUSTED_PROXIES=127.0.0.1,10.0.0.1
    # IMPORTANT: adaugă DOAR IP-urile serverelor tale de proxy, nu IP-uri publice arbitrare.
    TRUSTED_PROXIES: str = ""

    @property
    def allowed_origins_list(self) -> list:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_proxies_set(self) -> set:
        """Set de IP-uri proxy de încredere pentru validarea X-Forwarded-For."""
        return {ip.strip() for ip in self.TRUSTED_PROXIES.split(",") if ip.strip()}

    class Config:
        env_file = ".env"


settings = Settings()
