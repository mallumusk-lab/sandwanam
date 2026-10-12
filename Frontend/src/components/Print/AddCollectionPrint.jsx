
import React, { useEffect, useRef, useState } from "react";
import { useReactToPrint } from "react-to-print";
import { FiPrinter } from "react-icons/fi";
import "./Print.css";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faScissors } from "@fortawesome/free-solid-svg-icons";
import { useLocation, useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";

const Logo1 = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    <div style={{ borderRadius: "50%", overflow: "hidden" }}>
      <img
        src="https://i.postimg.cc/1XXXQfKn/logo1.png"
        alt="Logo"
        style={{ width: "40px", height: "40px" }}
      />
    </div>
  </div>
);

const Logo2 = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    <div style={{ borderRadius: "50%", overflow: "hidden" }}>
      <img
        src="https://i.postimg.cc/CLZ5rn19/logo2.png"
        alt="Logo"
        style={{ width: "40px", height: "40px" }}
      />
    </div>
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

const AddCollectionPrint = () => {
  const navigate = useNavigate();
  const [statementData, setStatementData] = useState([]);
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);

  const loanNumber = queryParams.get("loan_number");
  const name = queryParams.get("name");
  const collectionAmount = queryParams.get("amount");

  const userType = useSelector((state) => state.myfin.user);
  const userRole = useSelector((state) => state.myfin.data);

  const componentRef = useRef();
  const handlePrint = useReactToPrint({
    content: () => componentRef.current,
    pageStyle: `@media print { 
      @page { size: A4 portrait !important; margin: 5mm 5mm !important; } 
      .print-container { 
         padding: 0 !important;
         display: flex !important; 
         flex-direction: column !important; 
         justify-content: space-between !important;
         height: 285mm !important;
         gap: 0 !important;
      } 
    }`,
  });

  const currentDate = new Date();
  const formattedDate = `${currentDate.getDate()}/${currentDate.getMonth() + 1}/${currentDate.getFullYear()}`;

  let userInfo;
  if (userRole === "Admin") {
    userInfo = userType === "User1" ? User1Info : User2Info;
  } else {
    userInfo = userRole === "User1" ? User1Info : User2Info;
  }

  useEffect(() => {
    fetchData();
  }, [loanNumber]);

  const fetchData = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/statement/${loanNumber}`, {
        headers: {
          "Content-Type": "application/json",
          "x-api-key": "12345",
        },
      });
      if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
      const data = await response.json();
      setStatementData(data);
    } catch (error) {
      console.error("Error fetching data:", error.message);
    }
  };

  const lastStatement = statementData[statementData.length - 1] || {};
  const principalPaid = parseFloat(collectionAmount) || 0;
  const interestPaid = parseFloat(lastStatement.currentinterest) || 0;
  const totalPaid = principalPaid + interestPaid;

  const RenderContent = ({ copyTitle }) => (
    <div className="receipt-card">
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
        <h2 className="doc-title">{copyTitle || "Collection Receipt"}</h2>
        <div className="doc-date">Date: {formattedDate}</div>
      </div>

      <div className="info-grid">
        <div className="info-item">
          <span className="info-label">Customer Name</span>
          <span className="info-value">{name}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Loan ID</span>
          <span className="info-value">{loanNumber}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Principal Paid</span>
          <span className="info-value">₹{principalPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Interest Paid</span>
          <span className="info-value">₹{interestPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </div>
      </div>

      <div className="summary-box">
        <div className="summary-row total">
          <span className="total-label">Total Received</span>
          <span className="total-value">₹{totalPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="summary-row" style={{ marginTop: '15px', borderTop: '1px solid #e5e7eb', paddingTop: '15px' }}>
          <span className="info-label">Outstanding Principal</span>
          <span className="info-value">₹{parseFloat(lastStatement.principlebalance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="summary-row">
          <span className="info-label">Outstanding Interest</span>
          <span className="info-value">₹{parseFloat(lastStatement.interestbalance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </div>
      </div>

      <div className="receipt-footer">
        <div className="footer-seal">
          Office Seal
        </div>
        <div className="footer-signature">
          <div className="sig-line">Authorized Signatory</div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="print-page-wrapper">
      <div className="no-print print-actions">
        <button onClick={() => navigate(-1)} className="btn-back">
          Back
        </button>
        <button onClick={handlePrint} className="btn-print">
          <FiPrinter size={18} /> Print Receipt
        </button>
      </div>

      <div ref={componentRef} className="print-container">
        <RenderContent copyTitle="Office Copy" />
        
        <div className="cut-line">
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
          <hr />
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
        </div>

        <RenderContent copyTitle="Customer Copy" />

      </div>
    </div>
  );
};

export default AddCollectionPrint;
