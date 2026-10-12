import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { Myaction } from "../../store/MyfinSlice";
import storedData from "../LocalStorage/Role";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import "./Login.css";

function Login() {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleLogin = async () => {
    if (username.trim() === "") {
      // setError("Username is required");
      return;
    }
    if (password.trim() === "") {
      setError("Password is required");
      return;
    }

    try {
      // Make API call to authenticate
      const response = await fetch(`${API_BASE_URL}/authenticate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": "12345",
        },
        body: JSON.stringify({
          userName: username,
          password: password,
        }),
      });

      if (response.ok) {
        const data = await response.json();

        const { role, message } = data;

        console.log(data);
        if (data.role === "Admin") {
          console.log("hhh",data);
        }
        // localStorage.setItem("myfinData", JSON.stringify(data));
        dispatch(Myaction.dataReducer({ data: data }));
        alert(message);
        if (role === "User1") {
          navigate("/admin", { state: { data: data } });
        } else if (role === "User2") {
          navigate("/admin", { state: { data: data } });
        } else if (role === "Admin") {
          navigate("/admin", { state: { data: data } });
        }
      } else {
        const errorData = await response.json();
        console.error("Authentication Error:", errorData);

        setError(errorData.detail || errorData.message || "Authentication failed");
      }
    } catch (error) {
      console.log("Error during authentication:", error);
      setError("An error occurred during authentication");
    }
  };

  useEffect(() => {
    handleLogin();
  }, [storedData]);

  return (
    <div className="login-page-wrapper">
      <div className="login-card">
        <div className="login-header">
          <h1 className="login-title">Welcome Back</h1>
          <p className="login-subtitle">Please enter your details</p>
        </div>

        <div className="form-group">
          <label className="form-label">Username</label>
          <input
            type="text"
            className="form-input"
            placeholder="Enter your username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Password</label>
          <input
            type="password"
            className="form-input"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && (
          <div className="login-error">
            {error}
          </div>
        )}

        <button
          className="btn-login"
          onClick={handleLogin}
        >
          Login
        </button>
      </div>
    </div>
  );
}

export default Login;
