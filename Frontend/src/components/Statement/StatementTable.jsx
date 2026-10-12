import React, { useState, useEffect } from "react";
import "./StatementTable.css";
import { FiPrinter } from "react-icons/fi";
import { useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import { faContactCard } from "@fortawesome/free-solid-svg-icons";

const StatementTable = ({ statementData: propData, onRemove, previewMode = false }) => {
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const loan_number = queryParams.get("loan_number");
  const [fetchedData, setFetchedData] = useState([]);
  const [showCalculations, setShowCalculations] = useState(false);

  useEffect(() => {
    if (!propData && loan_number) {
      fetchData();
    }
  }, [loan_number, propData]);

  const fetchData = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/statement/${loan_number}`, {
        headers: {
          "x-api-key": "12345",
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }

      const data = await response.json();
      setFetchedData(data);
    } catch (error) {
      console.error("Error fetching data:", error.message);
    }
  };

  const statementData = propData || fetchedData;

  return (
    <div className={previewMode ? "statement-preview-wrapper" : "statement-record-container"}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
        <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: '14px', color: '#475569', fontWeight: '600' }}>
          <input 
            type="checkbox" 
            checked={showCalculations} 
            onChange={(e) => setShowCalculations(e.target.checked)} 
            style={{ marginRight: '8px', cursor: 'pointer', width: '16px', height: '16px' }}
          />
          Verify Calculations
        </label>
      </div>
      <div className="rr">
        <table className="statement-table">
          <thead>
            <tr>
              <th className="text-center">#</th>
              <th>Date</th>
              <th className="text-right">Payment</th>
              <th className="text-right">Principal</th>
              <th className="text-right">Interest</th>
              <th className="text-right">Int. Bal</th>
              <th className="text-right">Princ. Bal</th>
              <th>Remarks</th>
              {onRemove && <th className="text-center">Action</th>}
            </tr>
          </thead>

          <tbody>
            {statementData.map((row, index) => {
              let principleModifiedAmount = 0;
              if (index > 0) {
                principleModifiedAmount =
                  statementData[index].principlebalance -
                  statementData[index - 1].principlebalance;
              }

              const isRemovable = onRemove && row.transactiontype !== "newLoan";
              
              // Verify calculations logic
              let daysPassed = 0;
              let interestGenerated = 0;
              let prevPrinc = 0;
              let calcRateDisplay = '18.00';
              
              if (index < statementData.length - 1) {
                const prevRow = statementData[index + 1];
                const prevDate = new Date(new Date(prevRow.date).getFullYear(), new Date(prevRow.date).getMonth(), new Date(prevRow.date).getDate());
                const currDate = new Date(new Date(row.date).getFullYear(), new Date(row.date).getMonth(), new Date(row.date).getDate());
                const diffTime = currDate - prevDate;
                daysPassed = Math.round(diffTime / (1000 * 60 * 60 * 24));
                
                prevPrinc = parseFloat(prevRow.principlebalance);
                const currIntBal = parseFloat(row.interestbalance);
                const prevIntBal = parseFloat(prevRow.interestbalance);
                
                let intPaidReal = parseFloat(row.currentinterest || 0);
                if (row.transactiontype === 'compounding') {
                   // compounding sets currentinterest = -interest_due to hide from UI payment column conventionally
                   intPaidReal = 0; 
                }
                
                // For non-compounding, what was charged vs paid
                // Generated = NewBalance - OldBalance + Paid
                interestGenerated = currIntBal - prevIntBal + intPaidReal;
                if (row.transactiontype === 'compounding') {
                    interestGenerated = parseFloat(Math.abs(row.currentinterest || 0));
                }
                
                if (prevPrinc > 0) {
                    if (daysPassed > 0) {
                        let rate = (interestGenerated * 36500) / (prevPrinc * daysPassed);
                        // snap to common integers if very close
                        if (Math.abs(rate - Math.round(rate)) < 0.05) rate = Math.round(rate);
                        calcRateDisplay = rate.toFixed(2);
                    } else if (interestGenerated > 0) {
                        // This happens if same-day transactions have interest (usually shouldn't but good for debugging)
                        calcRateDisplay = "ERR"; 
                    }
                }
              }

              return (
                <React.Fragment key={index}>
                  <tr>
                    <td className="text-center" style={{ color: '#94a3b8' }}>{index + 1}</td>
                    <td style={{ fontWeight: 600 }}>
                      {new Date(row.date).toLocaleString('en-GB', { 
                        day: '2-digit', 
                        month: '2-digit', 
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </td>
                    <td className="text-right">
                      {row.transactiontype === "modify" ? "-" : parseFloat(row.amountpaid).toLocaleString(undefined, {minimumFractionDigits: 2})}
                    </td>
                    <td className="text-right">
                      {parseFloat(row.currentprincipal) < 0 
                        ? Math.abs(row.currentprincipal).toLocaleString(undefined, {minimumFractionDigits: 2})
                        : ""}
                    </td>
                    <td className="text-right">
                      {row.transactiontype === "compounding" ? "" : parseFloat(row.currentinterest).toLocaleString(undefined, {minimumFractionDigits: 2})}
                    </td>
                    <td className="text-right">
                      {parseFloat(row.interestbalance).toLocaleString(undefined, {minimumFractionDigits: 2})}
                    </td>
                    <td className="text-right balance-cell">
                      {parseFloat(row.principlebalance).toLocaleString(undefined, {minimumFractionDigits: 2})}
                    </td>
                    <td className="remark-cell">
                      {parseFloat(row.currentprincipal) > 0 && index < statementData.length - 1
                        ? `Principle increased by ${Math.abs(row.currentprincipal).toLocaleString()}`
                        : row.transactiontype === "newLoan" || row.transactiontype === "disbursement"
                        ? `New Loan: ${parseFloat(row.principlebalance).toLocaleString()}`
                        : row.transactiontype === "addColl"
                        ? `Collection: ${parseFloat(row.amountpaid).toLocaleString()}`
                        : row.transactiontype === "modify"
                        ? `Adjustment: ${parseFloat(Math.abs(principleModifiedAmount)).toLocaleString()}`
                        : row.transactiontype === "writeoff"
                        ? `Closed: ${parseFloat(row.principlebalance).toLocaleString()}`
                        : row.transactiontype}
                    </td>
                    {onRemove && (
                      <td className="text-center">
                        {isRemovable && (
                          <button 
                            className="btn-remove-lite" 
                            onClick={() => onRemove(row.originalIndex)}
                            title="Remove this entry"
                          >
                            ×
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                  {showCalculations && index < statementData.length - 1 && (
                     <tr className="calculation-row no-print" style={{ backgroundColor: '#f8fafc', fontSize: '0.85rem', color: '#64748b' }}>
                       <td colSpan={onRemove ? "9" : "8"} style={{ padding: '8px 12px', borderBottom: '1px solid #e2e8f0', borderTop: 'none', textAlign: 'left' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px' }}>
                             <span><strong style={{color: '#475569'}}>Time elapsed:</strong> {daysPassed} day(s)</span>
                             <span><strong style={{color: '#475569'}}>Interest applied:</strong> {prevPrinc.toLocaleString()} × {calcRateDisplay}% × {daysPassed} / 365 = <strong>{interestGenerated.toLocaleString(undefined, {minimumFractionDigits: 2})}</strong></span>
                             <span><strong style={{color: '#475569'}}>Int Paid:</strong> {row.transactiontype === "compounding" ? "0.00" : parseFloat(row.currentinterest || 0).toLocaleString()}</span>
                             <span><strong style={{color: '#475569'}}>Remaining Int Bal:</strong> {parseFloat(row.interestbalance).toLocaleString()}</span>
                          </div>
                       </td>
                     </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default StatementTable;
