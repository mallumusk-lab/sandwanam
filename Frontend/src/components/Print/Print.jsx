
import React, { useEffect, useRef, useState } from "react";
import { useReactToPrint } from "react-to-print";
import { FiPrinter } from "react-icons/fi";
import "./Print.css";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faScissors } from "@fortawesome/free-solid-svg-icons";
import { useLocation, useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";

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

const Print = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);

  // Extract loan details
  const loanNumber = queryParams.get("loan_number");
  const particulars = queryParams.get("particulars");
  const numberOfItems = queryParams.get("numberOfItems");
  const weight = queryParams.get("weight");
  const netWeight = queryParams.get("netWeight");
  const principleAmount = queryParams.get("principleAmount");
  const currentInterest = queryParams.get("currentInterest");
  const loanStartDate = queryParams.get("loanStartDate");
  const interest = queryParams.get("interest");
  const phone = queryParams.get("phone");
  const name = queryParams.get("name");
  const user_id = queryParams.get("user_id");
  const tenure = queryParams.get("tenure");
  const deduction = queryParams.get("deduction");

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
        <h2 className="doc-title">{copyTitle || "Loan Voucher"}</h2>
        <div className="doc-date">Date: {formattedDate}</div>
      </div>

      <div className="info-grid">
        <div className="info-item">
          <span className="info-label">Loan ID</span>
          <span className="info-value">{loanNumber}</span>
        </div>
        <div className="info-item">
          <span className="info-label">A/c Number</span>
          <span className="info-value">{user_id}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Customer Name</span>
          <span className="info-value">{name}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Phone</span>
          <span className="info-value">{phone}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Loan Date</span>
          <span className="info-value">
            {loanStartDate && !isNaN(new Date(loanStartDate).getTime()) 
              ? new Date(loanStartDate).toLocaleString() 
              : "N/A"}
          </span>
        </div>
        <div className="info-item">
          <span className="info-label">Tenure</span>
          <span className="info-value">{tenure} Months</span>
        </div>
        <div className="info-item">
          <span className="info-label">Particulars</span>
          <span className="info-value">{particulars}</span>
        </div>
        <div className="info-item">
          <span className="info-label">No. of Items</span>
          <span className="info-value">{numberOfItems}</span>
        </div>
        <div className="info-item">
          <span className="info-label">Total Weight</span>
          <span className="info-value">{weight}g</span>
        </div>
        <div className="info-item">
          <span className="info-label">Deduction</span>
          <span className="info-value">{deduction}g</span>
        </div>
        <div className="info-item">
          <span className="info-label">Net Weight</span>
          <span className="info-value">{netWeight}g</span>
        </div>
        <div className="info-item">
          <span className="info-label">Interest Rate</span>
          <span className="info-value">{interest}%</span>
        </div>
      </div>

      <div className="summary-box">
        <div className="summary-row total">
          <span className="total-label">Principal Amount</span>
          <span className="total-value">
            ₹{parseFloat(principleAmount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </span>
        </div>
      </div>

      <div className="terms-section">
        <h4 className="terms-header">Terms & Conditions:</h4>
        <ul className="terms-list">
          <li>പണയ ഉരുപ്പടി 6 മാസത്തിനകം തിരികെ എടുത്തു കൊള്ളുകയൊ പലിശ അടച്ചു പണയം പുതുക്കുകയോ ചെയ്യാത്ത പക്ഷം പണയ ഉരുപ്പടി വിലയ്ക്ക് കൊടുത്തു തുക ഈടാക്കുന്നതാണ്</li>
          <li>പണയ ഉരുപ്പടികൾ തിരിച്ചെടുക്കുമ്പോൾ ഒരു ദിവസത്തിന് മുമ്പേ പണം അടയ്‌ക്കേണ്ടതാണ്.12 മാസം കഴിഞ്ഞാൽ യാതൊരു അറിയിപ്പും കൂടാതെ ഉരുപ്പടിയെ വിലയ്ക്കു കൊടുത്തു തുക ഈടാക്കുന്നതാണ്.</li>
          <li>ഉരുപ്പടി തിരികെ എടുക്കുന്ന സമയത്ത് ഈ രസീത് ഹാജരാക്കണം</li>
        </ul>
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

export default Print;
