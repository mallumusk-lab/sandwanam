
import React, { useRef, useState } from "react";
import { useReactToPrint } from "react-to-print";
import { FiPrinter } from "react-icons/fi";
import "../Print/Print.css";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faScissors } from "@fortawesome/free-solid-svg-icons";
import { useLocation, useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";

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

const CalculatorPrint = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);

  const name = queryParams.get("name");
  const phoneNumber = queryParams.get("phoneNumber");
  const particulars = queryParams.get("particulars"); // Address/Info
  const principleAmount = queryParams.get("principleAmount");
  const interest = queryParams.get("interest");
  const tenure = queryParams.get("tenure");

  const userType = useSelector((state) => state.myfin.user);
  const userRole = useSelector((state) => state.myfin.data);

  const componentRef = useRef();
  const handlePrint = useReactToPrint({
    content: () => componentRef.current,
  });

  const currentDate = new Date();
  const formattedDate = `${currentDate.getDate()}/${currentDate.getMonth() + 1}/${currentDate.getFullYear()}`;

  let userInfo;
  if (userRole === "Admin") {
    userInfo = userType === "User1" ? User1Info : User2Info;
  } else {
    userInfo = userRole === "User1" ? User1Info : User2Info;
  }

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
        <h2 className="doc-title">{copyTitle || "Loan Estimation"}</h2>
        <div className="doc-date">Date: {formattedDate}</div>
      </div>

      <div className="info-grid">
        <div className="info-item">
          <span className="info-label">Customer Name</span>
          <span className="info-value">{name}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Phone</span>
          <span className="info-value">{phoneNumber}</span>
        </div>
        <div className="info-item" style={{ gridColumn: 'span 2' }}>
          <span className="info-label">Note/Address</span>
          <span className="info-value">{particulars}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Interest Rate</span>
          <span className="info-value">{interest}%</span>
        </div>
        <div className="info-item">
          <span className="info-label">Tenure</span>
          <span className="info-value">{tenure} Months</span>
        </div>
      </div>

      <div className="summary-box">
        <div className="summary-row total">
          <span className="total-label">Estimated Principal</span>
          <span className="total-value">
            ₹{parseFloat(principleAmount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </span>
        </div>
      </div>

      <div className="receipt-footer">
        <div className="footer-seal">
          Estimate Only
        </div>
        <div className="footer-signature">
          <div className="sig-line">Consultant Signature</div>
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
          <FiPrinter size={18} /> Print Estimation
        </button>
      </div>

      <div ref={componentRef} className="print-container">
        <RenderContent copyTitle="Consultant Copy" />
        <div className="cut-line no-print">
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
          <hr />
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
        </div>
        <RenderContent copyTitle="Client Copy" />
        <div className="cut-line no-print">
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
          <hr />
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
        </div>
        <RenderContent copyTitle="Receipt" />
      </div>
    </div>
  );
};

export default CalculatorPrint;
