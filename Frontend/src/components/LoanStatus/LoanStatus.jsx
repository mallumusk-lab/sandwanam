import React, { useState, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import "./LoanMani.css";
import "./LoanStatus.css";
import { Myaction } from "../../store/MyfinSlice";
import { useNavigate } from "react-router-dom";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import { Link } from "react-router-dom";
import { IoIosRefresh } from "react-icons/io";
import { FiPrinter, FiEdit3, FiPlusCircle, FiFileText, FiTrash2, FiUser } from "react-icons/fi";

const LoanStatus = ({ customer, userData, data0 }) => {
  const navigate = useNavigate();
  const [isModalOpen, setModalOpen] = useState(false);
  const [collectionAmount, setCollectionAmount] = useState("");
  const [modifyMode, setModifyMode] = useState("Particulars Modification");
  const [amount, setAmount] = useState({});
  const [editingLoan, setEditingLoan] = useState(false);
  const dispatch = useDispatch();
  const [lnumber, setLNumber] = useState("");
  const [interest, setInterest] = useState(0);
  const [isClosingLoan, setClosingLoan] = useState(false);
  const [closingWriteoffLoan, setWriteoffClosingLoan] = useState(false);
  const [currentInterest, setCurrentInteres] = useState(0);
  const [successModalOpen, setSuccessModalOpen] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [selectedLoanDataForReceipt, setSelectedLoanDataForReceipt] = useState(null);
  const userRole = useSelector((state) => state.myfin.data);
  const [statement, setStatement] = useState([]);
  const [loans, setLoans] = useState([]);
  const [data, setData] = useState([]);
  const [buttonClicked, setButtonClicked] = useState(false);
  const [writeoff, setWriteoff] = useState(0);
  const [remainingBalance, setRemainingBalance] = useState(0);
  const [currentPrincipleClose, setCurrentPrincipleClose] = useState(0);
  const [currentInterestClose, setCurrentInterestClose] = useState(0);
  const [currentLoanClose, setCurrentLoanClose] = useState(0);
  const [loanDate, setLoanDate] = useState(null);
  const [items, setItems] = useState([]); // Dynamic list for multiple particulars
  const [activeRefreshInterest, setActiveRefreshInterest] = useState(0);
  const [activeRefreshPrincipal, setActiveRefreshPrincipal] = useState(0);

  const loanFullData = useSelector((state) => state.myfin.loanFullData);
  const loanDetailsOfCustomer = useSelector(
    (state) => state.myfin.loanDetailsOfCustomer
  );

  // Fetch all loans for this customer
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/all_loan_data`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": "12345",
          },
          body: JSON.stringify({ customerId: customer }),
        });

        if (!response.ok) throw new Error("Network response was not ok");

        const result = await response.json();
        if (!result.customerLoanData || result.customerLoanData.length === 0) {
          return;
        }
        setLoans(result.customerLoanData);

        const sortedLoanDetails = result.customerLoanData[0].LoanDetails.sort((a, b) => {
          // Rule 1: Open loans first
          if (a.loantype === "open" && b.loantype !== "open") return -1;
          if (a.loantype !== "open" && b.loantype === "open") return 1;
          
          // Rule 2: Newest date first within the same type
          return new Date(b.date) - new Date(a.date);
        });
        setData(sortedLoanDetails);
      } catch (error) {
        console.error("Error fetching data:", error);
      }
    };
    fetchData();
  }, [buttonClicked, customer]);

  // Refresh a single loan's interest from the backend
  const refreshHandler = async (loanNumber) => {
    try {
      const response = await fetch(`${API_BASE_URL}/loan_summary/${loanNumber}`, {
        headers: API_HEADERS,
      });
      if (response.ok) {
        const summary = await response.json();

        await fetch(`${API_BASE_URL}/refresh_loan`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": "12345",
          },
          body: JSON.stringify({
            refreshprincipleamount: summary.current_principal,
            refreshinterest: summary.current_interest.toFixed(2),
            loan_number: loanNumber,
          }),
        });

        const updatedLoansData = data.map((loan) => {
          if (loan.loan_number === loanNumber) {
            return {
              ...loan,
              refreshprincipleamount: summary.current_principal,
              refreshinterest: summary.current_interest.toFixed(2),
            };
          }
          return loan;
        });
        dispatch(Myaction.loanFullDataSelected(updatedLoansData));
        setData(updatedLoansData);
      }
    } catch (error) {
      console.error("Error refreshing loan:", error);
    }
  };

  const handleButtonClick = async (loanNumber, loanInterest, refreshInt, refreshPri) => {
    setLNumber(loanNumber);
    setInterest(loanInterest);
    setActiveRefreshInterest(refreshInt || 0);
    setActiveRefreshPrincipal(refreshPri || 0);
    const response = await fetch(`${API_BASE_URL}/single_loan/${loanNumber}`, {
      headers: API_HEADERS,
    });

    if (response.ok) {
      const datas = await response.json();
      datas.map((d) => {
        setAmount({
          loanid: d.loanid,
          principalAmount: d.principleAmount,
          loanNumber: d.loan_number,
          interest: loanInterest,
          date: d.date,
        });
      });
    }
    setModalOpen(true);
  };

  // Fetch loan summary when modal opens or loan number changes
  useEffect(() => {
    async function fetchApi() {
      if (!lnumber) return;
      try {
        const response = await fetch(`${API_BASE_URL}/loan_summary/${lnumber}`, {
          headers: API_HEADERS,
        });
        if (response.ok) {
          const summary = await response.json();
          setStatement(summary.statements);
          setCurrentInteres(summary.current_interest);

          if (summary.statements && summary.statements.length > 0) {
            setAmount({
              loanid: summary.statements[0].loanid,
              principalAmount: summary.current_principal,
              loanNumber: summary.loan_number,
              interest: interest,
              date: summary.statements[0].date,
            });
            setActiveRefreshInterest(summary.current_interest);
            setActiveRefreshPrincipal(summary.current_principal);
          }
        }
      } catch (error) {
        console.error("Error fetching loan summary:", error);
      }
    }
    fetchApi();
  }, [isModalOpen, lnumber]);

  const handleModalClose = () => {
    setModalOpen(false);
    setCollectionAmount("");
    setWriteoffClosingLoan(false);
  };

  // Collection handlers — all calculations are done on the backend
  const handleCollectionSubmitCloseSevenDays = async (loanNumber, amount) => {
    try {
      const dateToday = new Date().toISOString();
      const response = await fetch(`${API_BASE_URL}/add_collection/${loanNumber}`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify({
          amountPaid: parseFloat(amount),
          date: dateToday,
          transactionType: "addColl",
          role: userRole || 'Admin',
        }),
      });
      if (!response.ok) throw new Error("Network response was not ok");
    } catch (error) {
      console.error("Error submitting seven days collection:", error);
      throw error;
    }
  };

  const handleCollectionSubmitClose = async (loanNumber, balance) => {
    try {
      const dateToday = new Date().toISOString();
      const response = await fetch(`${API_BASE_URL}/add_collection/${loanNumber}`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify({
          amountPaid: parseFloat(balance),
          date: dateToday,
          transactionType: "writeoff",
          role: userRole || 'Admin',
        }),
      });
      if (!response.ok) throw new Error("Network response was not ok");
    } catch (error) {
      console.error("Error submitting writeoff collection:", error);
      throw error;
    }
  };

  const handleCollectionSubmit = async (loanNumber, amount, isClosing = false) => {
    try {
      const dateToday = new Date().toISOString();
      const response = await fetch(`${API_BASE_URL}/add_collection/${loanNumber}`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify({
          amountPaid: parseFloat(amount),
          date: dateToday,
          transactionType: "addColl",
          is_closing: isClosing,
          role: userRole || 'Admin',
        }),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Network response was not ok");
      }
      
      if (!isClosing) {
        const currentAmount = amount;
        setSuccessMessage(`a collection of RS ${currentAmount} is done`);
        setSelectedLoanDataForReceipt({
          loanNumber: loanNumber,
          amount: currentAmount,
          name: data0.customername
        });
        setSuccessModalOpen(true);
        handleModalClose();
      }
    } catch (error) {
      console.error("Error submitting collection:", error);
      alert(`Error submitting collection: ${error.message}`);
      throw error;
    }
  };

  const handleViewStatement = (loan) => {
    navigate(`/statement?loan_number=${loan.loan_number}`);
  };

  const parseParticulars = (particularsStr) => {
    if (!particularsStr) return [];
    return particularsStr.split(", ").map(item => {
      // Handle "Name(Qty)" format
      const newFormatMatch = item.match(/^(.+)\((\d+)\)$/);
      if (newFormatMatch) {
        return { name: newFormatMatch[1], quantity: parseInt(newFormatMatch[2]) };
      }
      // Handle legacy "Qty Name" format
      const parts = item.split(" ");
      const quantity = parseInt(parts[0]);
      const name = parts.slice(1).join(" ");
      return { name, quantity };
    }).filter(item => !isNaN(item.quantity) && item.name);
  };

  const handleEditLoan = (loan) => {
    setEditingLoan({
      ...loan,
      principalAmount: 0 // Initialize to 0 as per the UI prompt instruction
    });
    setItems(parseParticulars(loan.particulars));
  };

  const updateItemQuantity = (name, amount) => {
    setItems(prev => prev.map(item => {
      if (item.name === name) {
        const newQty = Math.max(0, item.quantity + amount);
        return { ...item, quantity: newQty };
      }
      return item;
    }).filter(item => item.quantity > 0)); 
  };

  const handleEditLoanSubmit = async (printUrl) => {
    try {
      const serialParticulars = items.map(i => `${i.name}(${i.quantity})`).join(", ");
      
      const response1 = await fetch(
        `${API_BASE_URL}/edit_loan/${editingLoan.loan_number}`,
        {
          method: "POST",
          headers: API_HEADERS_JSON,
          body: JSON.stringify({
            particulars: serialParticulars,
            principleAmount: modifyMode === "Principal Addition" ? String(editingLoan.principalAmount) : "0",
            transactionType: "modify",
            role: userRole || 'Admin',
          }),
        }
      );
      if (!response1.ok) throw new Error("Network response was not ok for edit_loan");

      const response2 = await fetch(`${API_BASE_URL}/update-particulars`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify({
          loan_number: editingLoan.loan_number,
          new_particulars: serialParticulars,
        }),
      });
      if (!response2.ok) throw new Error("Network response was not ok for update-particulars");

      alert("Loan edited successfully!");
      setEditingLoan(false);
      setButtonClicked(!buttonClicked); 

      if (printUrl) {
          navigate(printUrl);
      }
    } catch (error) {
      console.error("Error editing loan:", error);
    }
  };

  const closeLoanHandler = async (
    refreshPrincipleAmountClose,
    refreshInterestClose,
    loanNumber,
    loanDate
  ) => {
    try {
      // Fetch fresh summary with is_closing=true to enforce the 7-day rule
      const response = await fetch(`${API_BASE_URL}/loan_summary/${loanNumber}?is_closing=true`, {
        headers: API_HEADERS,
      });
      
      let finalInterest = refreshInterestClose;
      let finalPrincipal = refreshPrincipleAmountClose;
      
      if (response.ok) {
        const summary = await response.json();
        finalInterest = summary.current_interest;
        finalPrincipal = summary.current_principal;
      }

      const totalAmount = parseFloat(finalPrincipal) + parseFloat(finalInterest);
      setWriteoff(totalAmount);
      setRemainingBalance(totalAmount);
      setCurrentInterestClose(finalInterest);
      setCurrentPrincipleClose(finalPrincipal);
      setCurrentLoanClose(loanNumber);
      setLNumber(loanNumber);
      setWriteoffClosingLoan(true);
      setLoanDate(loanDate);
    } catch (error) {
      console.error("Error fetching closing summary:", error);
    }
  };

  const handleCloseLoan = async () => {
    try {
      const loanStartDate = new Date(loanDate);
      const currentDate = new Date();
      const daysDifference =
        Math.abs(Math.ceil((currentDate - loanStartDate) / (1000 * 60 * 60 * 24))) + 1;

      const userConfirmed = window.confirm("Are you sure you want to close the loan?");
      if (!userConfirmed) return;

      if (daysDifference <= 6) {
        await handleCollectionSubmitCloseSevenDays(currentLoanClose, remainingBalance);
      } else {
        await handleCollectionSubmit(currentLoanClose, collectionAmount || 0, true);
      }
      await handleCollectionSubmitClose(currentLoanClose, remainingBalance);

      const response = await fetch(`${API_BASE_URL}/loan_type`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify({ loan_number: currentLoanClose, loanType: "closed" }),
      });
      if (!response.ok) throw new Error("Network response was not ok for update loan_type");

      alert("Loan closed successfully!");
      setButtonClicked(!buttonClicked); 
      setWriteoffClosingLoan(false); 
    } catch (error) {
      console.error("Error closing loan:", error);
      alert("Error closing loan: " + error.message);
    } finally {
      setClosingLoan(false);
      setCollectionAmount("");
    }
  };

  const amountReduction = (e) => {
    let val = e.target.value;
    
    // Remove leading zeros but keep a single '0'
    val = val.replace(/^0+(?=\d)/, '');
    
    // Ensure amount does not exceed the total payable (writeoff)
    if (parseFloat(val || 0) > writeoff) {
      return; 
    }
    
    setCollectionAmount(val);
    setRemainingBalance(writeoff - parseFloat(val || 0));
  };

  return (
    <>
      <main className="main-portfolio">
        <h1 className="portfolio-title">Loan Portfolio</h1>
        
        <div className="loans-list">
          {data.map((loan, index) => (
            <div key={index} className="loan-card">

              <div className="loan-card-header">
                <span className={`status-badge ${loan.loantype === "open" ? "status-active" : "status-closed"}`}>
                  {loan.loantype === "open" ? "Active Loan" : "Closed Loan"}
                </span>
                <span className="loan-number-tag">Loan ID: {loan.loan_number}</span>
              </div>

              <div className="loan-grid">
                <div className="metric-card">
                  <span className="metric-label">Start Date</span>
                  <span className="metric-value" style={{ fontSize: '0.9rem' }}>
                    {new Date(loan.date).toLocaleString()}
                  </span>
                </div>

                <div className="metric-card">
                  <span className="metric-label">Principal Amount</span>
                  <span className="metric-value highlight">
                    ₹{parseFloat(loan.refreshprincipleamount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>

                {loan.loantype === "open" && (
                  <div className="metric-card">
                    <span className="metric-label">Current Interest</span>
                    <span className="metric-value" style={{ color: '#f59e0b' }}>
                      ₹{parseFloat(loan.refreshinterest || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}
              </div>

              <div className="loan-grid">
                <div className="metric-card">
                  <span className="metric-label">Particulars</span>
                  <div className="particulars-list">
                    {loan.particulars?.split(',').map((p, i) => (
                      <span key={i} className="particular-tag">{p.trim()}</span>
                    )) || <span className="info-value">N/A</span>}
                  </div>
                </div>

                <div className="metric-card">
                  <span className="metric-label">Qty / Net Weight</span>
                  <span className="info-value">
                    {loan.number_of_items || 0} Qty | {loan.net_weight || 0}g (Net)
                  </span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Total / Deduction</span>
                  <span className="info-value">
                    {loan.weight || 0}g (T) | {loan.deduction || 0}g (D)
                  </span>
                </div>

                <div className="metric-card">
                  <span className="metric-label">Tenure / Rate</span>
                  <span className="info-value">
                    {loan.tenure || 0} Mo | {loan.interest || 0}%
                  </span>
                </div>
              </div>

              {/* Action buttons */}
              <div className="action-buttons-group">
                {(userRole === "Admin" || userRole === "User1" || userRole === "User2") &&
                  loan.loantype === "open" && (
                    <Link
                      to={`/print?loan_number=${loan.loan_number}&particulars=${loan.particulars}&numberOfItems=${loan.number_of_items}&weight=${loan.weight}&netWeight=${loan.net_weight}&principleAmount=${loan.principle_amount || loan.refreshprincipleamount}&currentInterest=${loan.refreshinterest}&loanStartDate=${loan.date}&interest=${loan.interest}&name=${data0.customername}&phone=${data0.phone}&user_id=${data0.user_id}&tenure=${loan.tenure}&deduction=${loan.deduction}`}
                    >
                      <button className="btn-premium btn-primary"><FiPrinter /> Print</button>
                    </Link>
                  )}

                {(userRole === "Admin" || userRole === "User1" || userRole === "User2") &&
                  loan.loantype === "open" && (
                    <button
                      className="btn-premium btn-outline"
                      onClick={() => handleEditLoan(loan)}
                    >
                      <FiEdit3 /> Modify
                    </button>
                  )}

                {loan.loantype === "open" && (
                  <button
                    className="btn-premium btn-outline"
                    onClick={() => handleButtonClick(loan.loan_number, loan.interest, loan.refreshinterest, loan.refreshprincipleamount)}
                  >
                    <FiPlusCircle /> Add Collection
                  </button>
                )}

                <button 
                  className="btn-premium btn-outline"
                  onClick={() => handleViewStatement(loan)}
                >
                  <FiFileText /> View Statement
                </button>

                {(userRole === "Admin" || userRole === "User1" || userRole === "User2") &&
                  loan.loantype === "open" && (
                    <button
                      className="btn-premium btn-danger"
                      onClick={() =>
                        closeLoanHandler(
                          loan.refreshprincipleamount,
                          loan.refreshinterest,
                          loan.loan_number,
                          loan.date
                        )
                      }
                    >
                      <FiTrash2 /> Close Loan
                    </button>
                  )}

                {loan.loantype === "closed" && (
                  <Link
                    to={`/editloan?loan_number=${loan.loan_number}&particulars=${loan.particulars}&numberOfItems=${loan.number_of_items || loan.numberOfItems}&weight=${loan.weight}&netWeight=${loan.net_weight}&principleAmount=${loan.refreshprincipleamount}&currentInterest=${loan.refreshinterest}&loanStartDate=${loan.date}&interest=${loan.interest}&name=${data0.customername}&phone=${data0.phone}&user_id=${data0.user_id}&tenure=${loan.tenure}&deduction=${loan.deduction}&remainingBalance=${loan.refreshprincipleamount}`}
                  >
                    <button className="btn-premium btn-primary"><FiPrinter /> Close Loan Print</button>
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      </main>
      
      {/* Edit Loan Modal */}
      {editingLoan && (
        <div className="modal-overlay">
          <div className="premium-modal">
            <button className="modal-close-btn" onClick={() => setEditingLoan(null)} title="Close">
              &times;
            </button>
            <h2>Edit Loan</h2>
            
            <div className="modal-input-group" style={{ marginBottom: '20px' }}>
              <label style={{ marginBottom: '8px', display: 'block' }}>Modification Type</label>
              <div style={{ display: 'flex', gap: '8px', background: '#f1f5f9', padding: '6px', borderRadius: '16px' }}>
                <button
                  type="button"
                  className="btn-premium"
                  style={{ flex: 1, justifyContent: 'center', backgroundColor: modifyMode === "Particulars Modification" ? 'white' : 'transparent', color: modifyMode === "Particulars Modification" ? 'var(--primary-purple)' : '#64748b', boxShadow: modifyMode === "Particulars Modification" ? '0 4px 6px -1px rgba(0,0,0,0.05)' : 'none', border: 'none', padding: '10px', borderRadius: '12px', fontWeight: 600, fontSize: '0.85rem' }}
                  onClick={() => {
                    setModifyMode("Particulars Modification");
                    setEditingLoan({ ...editingLoan, principalAmount: 0 });
                  }}
                >
                  Modify Items
                </button>
                <button
                  type="button"
                  className="btn-premium"
                  style={{ flex: 1, justifyContent: 'center', backgroundColor: modifyMode === "Principal Addition" ? 'white' : 'transparent', color: modifyMode === "Principal Addition" ? 'var(--primary-purple)' : '#64748b', boxShadow: modifyMode === "Principal Addition" ? '0 4px 6px -1px rgba(0,0,0,0.05)' : 'none', border: 'none', padding: '10px', borderRadius: '12px', fontWeight: 600, fontSize: '0.85rem' }}
                  onClick={() => setModifyMode("Principal Addition")}
                >
                  Add Principal
                </button>
              </div>
            </div>

            {modifyMode === "Particulars Modification" && (
              <div className="modal-section">
                <span className="metric-label">Items Inventory</span>
                <div className="item-list-container">
                  {items.map((item, index) => (
                    <div key={index} className="item-pill">
                      <span style={{ fontWeight: 600 }}>{item.name}</span>
                      <div className="qty-control">
                        <button className="qty-btn" onClick={() => updateItemQuantity(item.name, -1)}>-</button>
                        <span style={{ minWidth: "20px", textAlign: "center" }}>{item.quantity}</span>
                        <button className="qty-btn" onClick={() => updateItemQuantity(item.name, 1)}>+</button>
                        <button 
                          className="qty-btn" 
                          style={{ marginLeft: '8px', color: 'var(--danger-red)' }}
                          onClick={() => setItems(prev => prev.filter(i => i.name !== item.name))}
                        >
                          &times;
                        </button>
                      </div>
                    </div>
                  ))}
                  {items.length === 0 && <p style={{ fontSize: "0.85rem", color: "#64748b", textAlign: "center" }}>No items added yet</p>}
                </div>
              </div>
            )}

            {modifyMode === "Principal Addition" && (
              <div className="modal-input-group">
                <label>Principal Amount to Add</label>
                <input
                  type="number"
                  className="premium-input"
                  value={editingLoan.principalAmount}
                  onChange={(e) => setEditingLoan({ ...editingLoan, principalAmount: e.target.value })}
                />
              </div>
            )}

            <button
              className="btn-premium btn-primary"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={(e) => {
                e.preventDefault();
                const printUrl = `/modifyprint?modificationType=${encodeURIComponent(modifyMode)}&loan_number=${editingLoan.loan_number}&particulars=${encodeURIComponent(editingLoan.particulars || "")}&numberOfItems=${items.reduce((acc, i) => acc + i.quantity, 0)}&weight=${editingLoan.weight}&netWeight=${editingLoan.deduction}&principleAmount=${editingLoan.refreshprincipleamount}&currentInterest=${editingLoan.refreshinterest}&loanStartDate=${editingLoan.date}&interest=${editingLoan.interest}&name=${data0.customername}&phone=${data0.phone}&user_id=${data0.user_id}&tenure=${editingLoan.tenure}&deduction=${editingLoan.net_weight}&writeofamount=${remainingBalance}&principalAmount=${modifyMode === "Principal Addition" ? editingLoan.principalAmount : 0}&editparticulars=${encodeURIComponent(items.map(i => `${i.name}(${i.quantity})`).join(", "))}`;

                if (modifyMode === "Particulars Modification") {
                  if (items.length === 0) {
                    alert("Please add at least one item.");
                  } else {
                    handleEditLoanSubmit(printUrl);
                  }
                } else if (modifyMode === "Principal Addition") {
                  const principalAmountStr = editingLoan.principalAmount.toString().trim();
                  if (principalAmountStr === "" || principalAmountStr === "0" || isNaN(principalAmountStr)) {
                    alert("Please enter a valid numeric value for Principal Amount.");
                  } else {
                    handleEditLoanSubmit(printUrl);
                  }
                }
              }}
            >
              Save Changes
            </button>
          </div>
        </div>
      )}

{/* Close Loan (write-off) Modal */}
{closingWriteoffLoan && (
  <div className="modal-overlay">
    <div className="premium-modal">
      <button className="modal-close-btn" onClick={handleModalClose} title="Close">
        &times;
      </button>
      <h2>Close Loan</h2>
      
      <div className="modal-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span className="info-label">Principal</span>
          <span className="info-value">₹{parseFloat(currentPrincipleClose).toLocaleString()}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
          <span className="info-label">Interest</span>
          <span className="info-value">₹{parseFloat(currentInterestClose).toLocaleString()}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px dashed #cbd5e1', paddingTop: '8px' }}>
          <span className="info-label" style={{ color: 'var(--text-main)' }}>Total Payable</span>
          <span className="info-value" style={{ color: 'var(--primary-purple)', fontWeight: 700 }}>₹{parseFloat(writeoff).toLocaleString()}</span>
        </div>
      </div>

      <div className="modal-input-group">
        <label>Enter Collection Amount</label>
        <input
          type="number"
          className="premium-input"
          value={collectionAmount}
          onChange={(e) => amountReduction(e)}
          placeholder="0.00"
        />
        {remainingBalance > 0 && (
          <p style={{ fontSize: '0.8rem', color: 'var(--danger-red)', marginTop: '0.5rem' }}>
            Write-off Amount: ₹{parseFloat(remainingBalance).toLocaleString()}
          </p>
        )}
      </div>

      <button
        className="btn-premium btn-danger"
        style={{ width: '100%', justifyContent: 'center' }}
        onClick={() => handleCloseLoan()}
      >
        Confirm & Close Loan
      </button>
    </div>
  </div>
)}

{/* Add Collection Modal */}
{isModalOpen && (
  <div className="modal-overlay">
    <div className="premium-modal">
      <button className="modal-close-btn" onClick={handleModalClose} title="Close">
        &times;
      </button>
      <h2>Add Collection</h2>
      
      <div className="modal-section" style={{ backgroundColor: '#eef2ff' }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
          <span className="info-label">Outstanding Interest</span>
          <span className="info-value">₹{parseFloat(activeRefreshInterest).toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span className="info-label">Outstanding Principal</span>
          <span className="info-value">₹{parseFloat(activeRefreshPrincipal).toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
        </div>
      </div>

      <div className="modal-input-group">
        <label>Payment Amount</label>
        <input
          className="premium-input"
          value={collectionAmount}
          placeholder="Enter amount to pay"
          onChange={(e) => {
            const value = e.target.value;
            if (/^\d*$/.test(value)) {
              setCollectionAmount(value);
            }
          }}
          autoFocus
        />
      </div>

      <div className="modal-section">
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
          <span className="info-label">To Interest</span>
          <span className="info-value" style={{ color: 'var(--primary-purple)' }}>
            ₹{(Math.min(parseFloat(collectionAmount) || 0, parseFloat(activeRefreshInterest) || 0)).toLocaleString(undefined, {minimumFractionDigits: 2})}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span className="info-label">To Principal</span>
          <span className="info-value" style={{ color: 'var(--primary-purple)' }}>
             ₹{(Math.max(0, (parseFloat(collectionAmount) || 0) - (parseFloat(activeRefreshInterest) || 0))).toLocaleString(undefined, {minimumFractionDigits: 2})}
          </span>
        </div>
      </div>

      <button
        className="btn-premium btn-primary"
        style={{ width: '100%', justifyContent: 'center' }}
        onClick={() => {
          if (collectionAmount.toString().trim() !== "") {
            handleCollectionSubmit(lnumber, collectionAmount);
          } else {
            alert("Please enter a valid amount.");
          }
        }}
      >
        Submit Payment
      </button>
    </div>
  </div>
)}
{/* Success Modal */}
{successModalOpen && (
  <div className="modal-overlay">
    <div className="premium-modal" style={{ textAlign: 'center' }}>
      <button className="modal-close-btn" onClick={() => setSuccessModalOpen(false)} title="Close">
        &times;
      </button>
      <div className="success-icon-wrapper">
        <div className="success-icon-circle">
          <svg className="checkmark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">
            <circle className="checkmark__circle" cx="26" cy="26" r="25" fill="none"/>
            <path className="checkmark__check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
          </svg>
        </div>
      </div>
      <h3 className="success-title">{successMessage}</h3>
      <button
        onClick={() => {
          setSuccessModalOpen(false);
          if (selectedLoanDataForReceipt) {
            navigate(
              `/adddcollection?loan_number=${selectedLoanDataForReceipt.loanNumber}&amount=${selectedLoanDataForReceipt.amount}&name=${selectedLoanDataForReceipt.name}`
            );
          }
        }}
        className="btn-premium btn-primary"
        style={{ width: '100%', justifyContent: 'center' }}
      >
        View Receipt
      </button>
    </div>
  </div>
)}
    </>
  );
};

export default LoanStatus;
