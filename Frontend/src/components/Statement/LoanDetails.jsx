import React from "react";
import { FiUser, FiHash, FiZap, FiTarget, FiPercent, FiClock, FiLayers, FiFileText } from "react-icons/fi";
import "./LoanDetails.css";

const LoanDetails = ({ loan, customer }) => {
  if (!loan) return null;

  return (
    <div className="loan-details-banner">
      {/* Top Row: Customer and Loan ID Only */}
      <div className="details-top-row">
        <div className="customer-profile">
          <div className="avatar-circle">
            <FiUser size={18} />
          </div>
          <div>
            <div className="details-label">Borrower Name</div>
            <div className="details-value" style={{ fontSize: "1.05rem" }}>
              {customer?.customerName || customer?.customername || "N/A"}
            </div>
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <div className="details-label"><FiHash size={12} /> Loan ID</div>
          <div className="details-value" style={{ fontSize: "1.05rem" }}>{loan.loan_number}</div>
        </div>
      </div>

      {/* Bottom Row: Compact 3-Column Metrics Grid */}
      <div className="details-grid">
        <div className="details-item">
          <div className="details-label"><FiZap /> Principal</div>
          <div className="details-value">₹{parseFloat(loan.principle_amount || 0).toLocaleString()}</div>
        </div>
        <div className="details-item">
          <div className="details-label"><FiTarget /> Gross / Net Wt</div>
          <div className="details-value">{loan.weight || 0}g / {loan.net_weight || 0}g</div>
        </div>
        <div className="details-item">
          <div className="details-label"><FiPercent /> Interest Rate</div>
          <div className="details-value">{loan.interest}% PM</div>
        </div>
        <div className="details-item">
          <div className="details-label"><FiClock /> Tenure</div>
          <div className="details-value">{loan.tenure} Months</div>
        </div>
        <div className="details-item">
          <div className="details-label"><FiLayers /> Items Qty</div>
          <div className="details-value">{loan.number_of_items || "1"}</div>
        </div>
        <div className="details-item">
          <div className="details-label"><FiFileText /> Particulars</div>
          <div className="details-value" style={{ fontWeight: 500, opacity: 0.9 }}>
            {loan.particulars || "N/A"}
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoanDetails;