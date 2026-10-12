import React, { useEffect, useState } from "react";
import { FiUser, FiPlusCircle } from "react-icons/fi";
import { useNavigate } from 'react-router-dom';
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import "./LoanStatus.css";

const Profile = ({ customer, data: propData }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(propData || {});

  useEffect(() => {
    if (!propData || Object.keys(propData).length === 0) {
      const fetchData = async () => {
        try {
          const response = await fetch(`${API_BASE_URL}/customers/${customer}`, {
            method: "GET",
            headers: {
              "x-api-key": "12345",
            },
          });
          const result = await response.json();
          setData(result);
        } catch (error) {
          console.log("Error fetching data:", error);
        }
      };
      fetchData();
    } else {
      setData(propData);
    }
  }, [customer, propData]);

  return (
    <aside className="customer-sidebar" style={{ width: '100%', margin: 0 }}>
      <div className="customer-card">
        <div className="customer-avatar-container">
          <FiUser size={40} color="var(--primary-purple)" />
        </div>
        <div className="customer-info">
          <h3>Customer Profile</h3>
          
          <div className="info-row">
            <span className="info-label">Name</span>
            <span className="info-value">{data.customername || "N/A"}</span>
          </div>
          
          <div className="info-row">
            <span className="info-label">Customer ID</span>
            <span className="info-value">{data.user_id || data.customerid || "N/A"}</span>
          </div>
          
          <div className="info-row">
            <span className="info-label">Phone Number</span>
            <span className="info-value">{data.phone || "N/A"}</span>
          </div>
          
          <div className="info-row">
            <span className="info-label">Address</span>
            <span className="info-value">{data.address || "N/A"}</span>
          </div>

          <button 
            className="btn-premium btn-primary" 
            style={{ width: '100%', marginTop: '1.5rem', justifyContent: 'center' }}
            onClick={() => navigate(`/newloan?customerid=${customer}`)}
          >
            <FiPlusCircle /> Add New Loan
          </button>
        </div>
      </div>
    </aside>
  );
};

export default Profile;


