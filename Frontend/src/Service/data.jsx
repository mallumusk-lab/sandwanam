import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "./Index";

export const fetchUserData = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/customers`, {
        method: "GET",
        headers: {
          "x-api-key": "12345",
        },
      });
      const result = await response.json();
      return result;

    } catch (error) {
      console.error("Error fetching data:", error);
      throw error;
    }
  };
  