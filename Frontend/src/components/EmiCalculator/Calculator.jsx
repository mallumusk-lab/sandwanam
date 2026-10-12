import React, { useState } from "react";
import { Link } from "react-router-dom";

const Calculator = () => {
  const [formData, setFormData] = useState({
    name: "",
    phoneNumber: "",
    particulars: "",
    principleAmount: "",
    interest: "",
    tenure: "",
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: value,
    });
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        backgroundColor: "var(--bg-app)",
        fontFamily: "var(--font-main)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "440px",
          padding: "40px",
          border: "2px solid var(--primary-light)",
          borderRadius: "var(--radius-lg)",
          backgroundColor: "var(--bg-glass)",
          backdropFilter: "blur(10px)",
          boxShadow: "var(--shadow-xl)",
        }}
      >
        <h2
          style={{
            textAlign: "center",
            marginTop: "0",
            marginBottom: "32px",
            fontFamily: "var(--font-heading)",
            color: "var(--text-heading)",
            fontSize: "28px"
          }}
        >
          EMI Calculator
        </h2>
        <div style={{ marginBottom: "20px" }}>
          <label>Name:</label>
          <input
            type="text"
            name="name"
            value={formData.name}
            onChange={handleChange}
                        style={{ width: "100%", padding: "12px", marginTop: "8px", border: "2px solid var(--border-subtle)", borderRadius: "var(--radius-md)", boxSizing: "border-box", transition: "all 0.3s ease", outline: "none" }}
            onFocus={(e) => { e.target.style.borderColor = "var(--primary)"; e.target.style.boxShadow = "0 0 0 4px var(--primary-light)"; }}
            onBlur={(e) => { e.target.style.borderColor = "var(--border-subtle)"; e.target.style.boxShadow = "none"; }}

          />
        </div>
        <div style={{ marginBottom: "20px", display: "flex", justifyContent: "space-between" }}>
          <div style={{ width: "48%" }}>
            <label>Phone Number:</label>
            <input
              type="text"
              name="phoneNumber"
              value={formData.phoneNumber}
              onChange={handleChange}
                          style={{ width: "100%", padding: "12px", marginTop: "8px", border: "2px solid var(--border-subtle)", borderRadius: "var(--radius-md)", boxSizing: "border-box", transition: "all 0.3s ease", outline: "none" }}
            onFocus={(e) => { e.target.style.borderColor = "var(--primary)"; e.target.style.boxShadow = "0 0 0 4px var(--primary-light)"; }}
            onBlur={(e) => { e.target.style.borderColor = "var(--border-subtle)"; e.target.style.boxShadow = "none"; }}

            />
          </div>
          <div style={{ width: "48%" }}>
            <label>Address:</label>
            <input
              type="text"
              name="particulars"
              value={formData.particulars}
              onChange={handleChange}
                          style={{ width: "100%", padding: "12px", marginTop: "8px", border: "2px solid var(--border-subtle)", borderRadius: "var(--radius-md)", boxSizing: "border-box", transition: "all 0.3s ease", outline: "none" }}
            onFocus={(e) => { e.target.style.borderColor = "var(--primary)"; e.target.style.boxShadow = "0 0 0 4px var(--primary-light)"; }}
            onBlur={(e) => { e.target.style.borderColor = "var(--border-subtle)"; e.target.style.boxShadow = "none"; }}

            />
          </div>
        </div>
        <div style={{ marginBottom: "20px", display: "flex", justifyContent: "space-between" }}>
          <div style={{ width: "48%" }}>
            <label>Principle Amount:</label>
            <input
              type="number"
              name="principleAmount"
              value={formData.principleAmount}
              onChange={handleChange}
                          style={{ width: "100%", padding: "12px", marginTop: "8px", border: "2px solid var(--border-subtle)", borderRadius: "var(--radius-md)", boxSizing: "border-box", transition: "all 0.3s ease", outline: "none" }}
            onFocus={(e) => { e.target.style.borderColor = "var(--primary)"; e.target.style.boxShadow = "0 0 0 4px var(--primary-light)"; }}
            onBlur={(e) => { e.target.style.borderColor = "var(--border-subtle)"; e.target.style.boxShadow = "none"; }}

            />
          </div>
          <div style={{ width: "48%" }}>
            <label>Interest:</label>
            <input
              type="number"
              name="interest"
              value={formData.interest}
              onChange={handleChange}
                          style={{ width: "100%", padding: "12px", marginTop: "8px", border: "2px solid var(--border-subtle)", borderRadius: "var(--radius-md)", boxSizing: "border-box", transition: "all 0.3s ease", outline: "none" }}
            onFocus={(e) => { e.target.style.borderColor = "var(--primary)"; e.target.style.boxShadow = "0 0 0 4px var(--primary-light)"; }}
            onBlur={(e) => { e.target.style.borderColor = "var(--border-subtle)"; e.target.style.boxShadow = "none"; }}

            />
          </div>
        </div>
        <div style={{ marginBottom: "20px" }}>
          <label>Tenure:</label>
          <input
            type="text"
            name="tenure"
            placeholder="Enter Tenure (in years)"
            value={formData.tenure}
            onChange={handleChange}
            style={{ width: "100%", padding: "12px", marginTop: "8px", border: "2px solid var(--border-subtle)", borderRadius: "var(--radius-md)", boxSizing: "border-box", transition: "all 0.3s ease", outline: "none" }}
            onFocus={(e) => { e.target.style.borderColor = "var(--primary)"; e.target.style.boxShadow = "0 0 0 4px var(--primary-light)"; }}
            onBlur={(e) => { e.target.style.borderColor = "var(--border-subtle)"; e.target.style.boxShadow = "none"; }}
          />
        </div>
        <Link
          to={{
            pathname: "/printcalculator",
            search: `?name=${formData.name}&phoneNumber=${formData.phoneNumber}&particulars=${formData.particulars}&principleAmount=${formData.principleAmount}&interest=${formData.interest}&tenure=${formData.tenure}`,
          }}
        >
          <button
            style={{
              width: "100%",
              backgroundColor: "var(--primary)",
              color: "white",
              padding: "16px",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: "16px",
              fontWeight: "700",
              transition: "all 0.3s ease",
              boxShadow: "var(--shadow-md)",
              marginTop: "16px"
            }}
            onMouseEnter={(e) => { e.target.style.backgroundColor = "var(--primary-hover)"; e.target.style.transform = "translateY(-2px)"; e.target.style.boxShadow = "var(--shadow-lg)"; }}
            onMouseLeave={(e) => { e.target.style.backgroundColor = "var(--primary)"; e.target.style.transform = "translateY(0)"; e.target.style.boxShadow = "var(--shadow-md)"; }}
          >
            Generate Print View
          </button>
        </Link>
      </div>
    </div>
  );
};

export default Calculator;
