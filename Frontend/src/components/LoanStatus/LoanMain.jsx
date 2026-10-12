import React from "react";
import Profile from "./Profile";
import LoanStatus from "./LoanStatus";
import { useState } from "react";
import { useEffect } from "react";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
// import { useSelector } from "react-redux";
const LoanMain = () => {
  const queryParams = new URLSearchParams(location.search);
  const customerid = queryParams.get("customerid");
  // const data = useSelector((state) => state.myfin.data);
  const userDataString = queryParams.get("userData");
  const userData = userDataString ? JSON.parse(userDataString) : null;

  const [data0, setData] = useState({});
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/customers/${customerid}`,
          {
            method: "GET",
            headers: {
              "x-api-key": "12345",
            },
          }
        );
        const result = await response.json();
        setData(result);
        // console.log(result);
      } catch (error) {
        console.log("Error fetching data:", error);
      }
    };

    fetchData();
  }, [customerid]);

  return (
    <div style={{ backgroundColor: "#F7FAFC", minHeight: "100vh", paddingBottom: "60px", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ height: "48px" }}></div>
      
      <div style={{ 
        display: "flex", 
        maxWidth: "1400px", 
        margin: "0 auto", 
        gap: "32px", 
        padding: "0 24px",
        flexWrap: "wrap"
      }}>
        <div style={{ flex: "1", minWidth: "320px" }}>
          <Profile customer={customerid} data={data0} />
        </div>
        <div style={{ flex: "2.5", minWidth: "600px" }}>
          <LoanStatus customer={customerid} userData={userData} data0={data0} />
        </div>
      </div>
    </div>
  );
};

export default LoanMain;
