/* Runtime configuration. On Render / Docker this file is regenerated from environment variables by
 * `node scripts/write-config.mjs` (see README). Edit by hand for a simple static host. */
window.OBDT_CONFIG = {
  BACKEND_BASE_URL: "http://localhost:8000",
  APP_ENV: "development",
  MOCK_MODE: "auto",            // auto | true | false
  API_KEY: "",
  AUTH_MODE: "none",            // none | password
  APP_PASSWORD_SHA256: "",      // hex SHA-256 of the access password when AUTH_MODE=password
  REQUEST_TIMEOUT_S: 45,
  LONG_TIMEOUT_S: 240,
  DEFAULT_PLANT: "IX-OB-01",
  APP_TITLE: "Industry-X Ore Beneficiation Twin"
};
