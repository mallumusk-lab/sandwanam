// eslint-disable-next-line no-unused-vars
import React, { useState } from "react";

import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import { FiUser, FiPhone, FiMapPin, FiSend } from "react-icons/fi";
import "./NewCustomer.css";

const NewCustomer = () => {
  const navigate = useNavigate();

  const userRole = useSelector((state) => state.myfin.data);
  const userType = useSelector((state) => state.myfin.user);
 

  const [formData, setFormData] = useState({
    name: "",
    phoneNumber: "",
    address: "",
  });

  const [formErrors, setFormErrors] = useState({});
  const [isFormSubmitted, setIsFormSubmitted] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prevData) => ({ ...prevData, [name]: value }));
  
    const phoneRegex = /^\d{10}$/;
    const nameRegex = /^[a-zA-Z\s]+$/;
    const addressRegex = /^[a-zA-Z0-9\s.,-]+$/;
  
    if (name === 'phoneNumber' && !phoneRegex.test(value)) {
      setFormErrors((prevErrors) => ({ ...prevErrors, [name]: "Invalid phone number" }));
    } else if (name === 'name' && !nameRegex.test(value)) {
      setFormErrors((prevErrors) => ({ ...prevErrors, [name]: "Invalid name" }));
    } else if (name === 'address' && !addressRegex.test(value)) {
      setFormErrors((prevErrors) => ({ ...prevErrors, [name]: "Invalid address" }));
    } else {
      setFormErrors((prevErrors) => ({ ...prevErrors, [name]: "" }));
    }
  };
  
  
  const handleSubmit = async (e) => {
    e.preventDefault();

    // Basic validation
    const errors = {};
    if (!formData.name) errors.name = "Name is required";
    if (!formData.phoneNumber) errors.phoneNumber = "Phone Number is required";
    if (!formData.address) errors.address = "Address is required";

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
    } else {
      try {
        // Fetch existing customers to get the count
        const customersResponse = await fetch(
          `${API_BASE_URL}/customers`,
          {
            method: "GET",
            headers: {
              "x-api-key": "12345",
            },
          }
        );

        if (!customersResponse.ok) {
          throw new Error("Failed to fetch customers");
        }

        const existingCustomers = await customersResponse.json();

        // Mapping object for role-to-prefix associations
        const rolePrefixMap = {
          Admin: "AD",
          User1: "SAN",
          User2: "SWA",
        };

        // Calculate the next user_id based on userData.role

        const prefix =
          rolePrefixMap[userRole === "Admin" ? userType : userRole];
        console.log("PREFIX " + prefix);
        if (!prefix) {
          throw new Error("Invalid user role");
        }

        // Calculate the next user_id based on prefix
        const samePrefixIds = existingCustomers
          .filter(c => c.user_id && c.user_id.startsWith(prefix))
          .map(c => {
            const numPart = parseInt(c.user_id.replace(prefix, ""));
            return isNaN(numPart) ? 0 : numPart;
          });
        
        const nextUserId = samePrefixIds.length > 0 ? Math.max(...samePrefixIds) + 1 : 1;

        // Form submitted successfully
        const response = await fetch(`${API_BASE_URL}/customers`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": "12345",
          },
          body: JSON.stringify({
            user_id: `${prefix}${nextUserId}`,
            customerName: formData.name,
            phone: formData.phoneNumber,
            address: formData.address,
            loanStatus: "0",
            role: userRole,
          }),
        });

        if (response.ok) {
          setIsFormSubmitted(true);
          alert("Registration Successful!");
          // window.location.href = '/admin';
          navigate("/admin");
        } else {
          throw new Error("Phone Number Already Exists");
        }
      } catch (error) {
        console.error(error);
        alert("Phone Number Already Exists");
      }
    }
  };

  return (
    <div className="new-customer-container">
      <div className="new-customer-card">
        <h2>Add New Customer</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>
              <FiUser size={14} /> Name
            </label>
            <div className="input-wrapper">
              <FiUser className="input-icon" />
              <input
                type="text"
                name="name"
                className="premium-input"
                placeholder="Enter customer name"
                value={formData.name}
                onChange={handleChange}
                required
              />
            </div>
            {formErrors.name && (
              <span className="error-message">{formErrors.name}</span>
            )}
          </div>

          <div className="form-group">
            <label>
              <FiPhone size={14} /> Phone Number
            </label>
            <div className="input-wrapper">
              <FiPhone className="input-icon" />
              <input
                type="text"
                name="phoneNumber"
                className="premium-input"
                placeholder="10-digit mobile number"
                value={formData.phoneNumber}
                onChange={handleChange}
                maxLength={10}
                required
              />
            </div>
            {formErrors.phoneNumber && (
              <span className="error-message">{formErrors.phoneNumber}</span>
            )}
          </div>

          <div className="form-group">
            <label>
              <FiMapPin size={14} /> Address
            </label>
            <div className="input-wrapper">
              <FiMapPin className="input-icon" style={{ top: '1.2rem' }} />
              <textarea
                name="address"
                className="premium-textarea"
                placeholder="Enter customer address"
                value={formData.address}
                onChange={handleChange}
                required
              />
            </div>
            {formErrors.address && (
              <span className="error-message">{formErrors.address}</span>
            )}
          </div>

          <button type="submit" className="btn-submit">
            <FiSend /> Submit Registration
          </button>

          {isFormSubmitted && (
            <div className="success-message">
              ✅ Registration Successful! Redirecting...
            </div>
          )}
        </form>
      </div>
    </div>
  );
};


export default NewCustomer;
