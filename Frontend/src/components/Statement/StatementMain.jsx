
import React, { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useSelector } from "react-redux";
import { useReactToPrint } from "react-to-print";
import { FiPrinter, FiArrowLeft } from "react-icons/fi";
import StatementTable from './StatementTable';
import LoanDetails from './LoanDetails';
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";

import "../Print/Print.css";
import "./StatementMain.css";

const Logo1 = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    <img src="https://i.postimg.cc/1XXXQfKn/logo1.png" alt="Logo" style={{ width: "40px", height: "40px" }} />
  </div>
);

const Logo2 = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    <img src="https://i.postimg.cc/CLZ5rn19/logo2.png" alt="Logo" style={{ width: "40px", height: "40px" }} />
  </div>
);

const User1Info = {
  header: "SANTHWANAM FINANCE PRIVATE LIMITED",
  place: "PINKULAM JUNCTION URAMBU ROAD, UCHAKKADA PO. PIN - 695506",
  mail: "santhwanam72@gmail.com",
  mob: "8089153752",
  logo: <Logo1 />,
};

const User2Info = {
  header: "SWATHANTRA FINANCE PRIVATE LIMITED",
  place: "VALAMKULAM POZHIYOOR ROAD POZHIYOOR PO. PIN - 695513",
  mail: "swathantrafinance52@gmail.com",
  mob: "8590678889",
  logo: <Logo2 />,
};

const StatementMain = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const loanNumber = queryParams.get("loan_number");
  const [loanData, setLoanData] = useState(null);
  const [customerData, setCustomerData] = useState(null);
  
  const userType = useSelector((state) => state.myfin.user);
  const userRole = useSelector((state) => state.myfin.data);
  const componentRef = useRef();

  const handlePrint = useReactToPrint({
    content: () => componentRef.current,
    pageStyle: `@media print { @page { size: portrait !important; margin: 8mm !important; } }`,
  });

  useEffect(() => {
    const fetchLoanData = async () => {
      if (!loanNumber) return;
      try {
        const response = await fetch(`${API_BASE_URL}/single_loan/${loanNumber}`, {
          headers: API_HEADERS,
        });
        if (response.ok) {
          const data = await response.json();
          if (data && data.length > 0) {
            const loan = data[0];
            setLoanData(loan);
            
            const custResponse = await fetch(`${API_BASE_URL}/customers/${loan.customerid}`, {
              headers: API_HEADERS,
            });
            if (custResponse.ok) {
              const custData = await custResponse.json();
              setCustomerData(custData);
            }
          }
        }
      } catch (error) {
        console.error("Error fetching statement main data:", error);
      }
    };
    fetchLoanData();
  }, [loanNumber]);

  let userInfo;
  if (userRole === "Admin") {
    userInfo = userType === "User1" ? User1Info : User2Info;
  } else {
    userInfo = userRole === "User1" ? User1Info : User2Info;
  }

  const currentDate = new Date();
  const formattedDate = `${currentDate.getDate()}/${currentDate.getMonth() + 1}/${currentDate.getFullYear()}`;

  return (
    <div className="print-page-wrapper">
      <div ref={componentRef} className="print-container">
        <div className="printable-statement">
          {/* Header Section */}
          <div className="receipt-header">
            <div className="header-logo-container">
              <div className="header-logo-circle">
                {userInfo.logo}
              </div>
            </div>
            <h1 className="comp-name">{userInfo.header}</h1>
            <p className="comp-address">{userInfo.place}</p>
            <div className="comp-contact">
              <span>Email: {userInfo.mail}</span>
              <span>|</span>
              <span>Mob: {userInfo.mob}</span>
            </div>
          </div>

          <div className="doc-title-container">
            <h2 className="doc-title">Loan Account Statement</h2>
            <div className="doc-date">Date: {formattedDate}</div>
          </div>

          <div className="loan-details-print-wrapper">
            <LoanDetails loan={loanData} customer={customerData} />
          </div>

          <div className="statement-table-container">
            <StatementTable />
          </div>
          
          {/* Footer Section - Hidden on screen, shown in print */}
          <div className="receipt-footer print-only-footer">
            <div className="footer-seal">
              <div className="seal-circle">Office Seal</div>
            </div>
            <div className="footer-signature">
              <div className="sig-line">Authorized Signatory</div>
              <div className="sig-subtext">S&S Finance Services</div>
            </div>
          </div>
        </div>
      </div>

      <div className="no-print print-actions" style={{ marginTop: '30px' }}>
        <button onClick={() => navigate(-1)} className="btn-back">
          <FiArrowLeft /> Back
        </button>
        <button onClick={handlePrint} className="btn-print">
          <FiPrinter size={18} /> Print Statement
        </button>
      </div>
    </div>
  );
}

export default StatementMain;
