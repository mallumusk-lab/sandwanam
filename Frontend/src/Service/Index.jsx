// export const API_BASE_URL = "http://43.204.202.44:3000";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const API_HEADERS = {
  "x-api-key": "12345"
};

export const API_HEADERS_JSON = {
  "Content-Type": "application/json",
  "x-api-key": "12345"
};
