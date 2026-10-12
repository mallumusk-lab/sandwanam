import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import { FiUser, FiPhone, FiMapPin, FiDollarSign, FiCalendar, FiPlus, FiTrash2, FiSend, FiArrowLeft, FiCheckCircle, FiSearch, FiHash, FiZap, FiTarget, FiPercent, FiClock, FiLayers, FiFileText, FiChevronDown, FiCheck } from "react-icons/fi";
import { IoIosRefresh } from "react-icons/io";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import StatementTable from "../Statement/StatementTable";
import "./History.css";

const CustomSelect = ({ label, value, options, onChange, placeholder = "Select Option" }) => {
  const [isOpen, setIsOpen] = useState(false);
  
  const handleSelect = (val) => {
    onChange(val);
    setIsOpen(false);
  };

  const selectedOption = options.find(opt => opt.value === value);

  return (
    <div className="custom-select-container">
      <div 
        className={`custom-select-trigger ${isOpen ? "active" : ""}`}
        onClick={() => setIsOpen(!isOpen)}
      >
        <span>{selectedOption ? selectedOption.label : placeholder}</span>
        <div className="custom-select-icon">
          <FiChevronDown />
        </div>
      </div>
      
      {isOpen && (
        <>
          <div className="dropdown-overlay-fixed" onClick={() => setIsOpen(false)} style={{position:'fixed', inset:0, zIndex: 99}} />
          <div className="custom-select-menu">
            {options.map((opt) => (
              <div 
                key={opt.value}
                className={`custom-select-option ${value === opt.value ? "selected" : ""}`}
                onClick={() => handleSelect(opt.value)}
              >
                {opt.label}
                {value === opt.value && <FiCheck className="option-check" />}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

const History = () => {
  const navigate = useNavigate();
  const userRole = useSelector((state) => state.myfin.data);
  const userType = useSelector((state) => state.myfin.user);

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  // Customer Selection State
  const [customerType, setCustomerType] = useState(""); // "", "new" or "existing"
  const [searchQuery, setSearchQuery] = useState("");
  const [customers, setCustomers] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState(null);

  // Step 1: New Customer Data (if not selected)
  const [customerData, setCustomerData] = useState({
    customerName: "",
    phone: "",
    address: "",
  });

  // Fetch customers on mount
  useEffect(() => {
    const fetchCustomers = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/customers`, { headers: API_HEADERS });
        if (res.ok) {
          const data = await res.json();
          setCustomers(data);
        }
      } catch (err) {
        console.error("Failed to fetch customers", err);
      }
    };
    fetchCustomers();
  }, []);

  const filteredCustomers = searchQuery.length > 0 
    ? customers.filter(c => {
        const name = c.customername ? c.customername.toLowerCase() : "";
        const phone = c.phone || "";
        const userId = c.user_id ? c.user_id.toLowerCase() : "";
        const query = searchQuery.toLowerCase();
        
        return name.includes(query) || phone.includes(query) || userId.includes(query);
      })
    : [];

  // Step 2: Loan Data
  const [loanData, setLoanData] = useState({
    principal: "",
    interest: "",
    tenure: "",
    date: new Date(),
    weight: "",
    deduction: "",
  });

  const [loanItems, setLoanItems] = useState([]);

  const updateLoanItem = (name, amount) => {
    setLoanItems(prev => prev.map(item => {
      if (item.name === name) {
        const newQty = Math.max(0, item.quantity + amount);
        return { ...item, quantity: newQty };
      }
      return item;
    }).filter(item => item.quantity > 0)); 
  };

  // Step 3: Collections
  const [collections, setCollections] = useState([]);
  const [previewData, setPreviewData] = useState([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [newEntry, setNewEntry] = useState({
    date: new Date(),
    type: "addColl",
    amount: ""
  });

  const getNextCompoundDate = () => {
    // Base date: last compounding event if any, otherwise loan start
    const compoundEvents = previewData.filter(c => c.transactiontype === "compounding");
    const baseDate = compoundEvents.length > 0
      ? new Date(Math.max(...compoundEvents.map(c => new Date(c.date))))
      : new Date(loanData.date);
    
    const next = new Date(baseDate);
    next.setDate(next.getDate() + 365);
    return next;
  };



  const addOneEntry = () => {
    if (!newEntry.amount || isNaN(newEntry.amount) || parseFloat(newEntry.amount) <= 0) {
      setError("Please enter a valid amount greater than 0.");
      return;
    }

    setCollections(prev => [...prev, { 
      ...newEntry, 
      date: new Date(newEntry.date),
      amount: newEntry.amount 
    }]);
    setNewEntry(prev => ({ ...prev, amount: "" }));
    setError("");
  };

  const updateCollection = (index, field, value) => {
    const newCollections = [...collections];
    newCollections[index][field] = value;
    setCollections(newCollections);
  };

  const sortCollections = () => {
    setCollections(prev => [...prev].sort((a, b) => new Date(a.date) - new Date(b.date)));
  };

  const removeCollection = (index) => {
    setCollections(collections.filter((_, i) => i !== index));
  };

  const fetchPreview = async () => {
    if (!loanData.principal || !loanData.date) return;
    setPreviewLoading(true);
    try {
      const payload = {
        customerType: customerType || "new",
        customerData: customerType === "new" ? { ...customerData, user_id: "PREVIEW1" } : null,
        selectedCustomerId: customerType === "existing" ? selectedCustomer?.customerid : null,
        loanData: {
          particulars: loanItems.map(i => `${i.name}(${i.quantity})`).join(",") || "Preview Items",
          number_of_items: loanItems.reduce((acc, i) => acc + i.quantity, 0).toString() || "1",
          weight: parseFloat(loanData.weight || 0),
          net_weight: parseFloat(loanData.weight || 0) - parseFloat(loanData.deduction || 0),
          principle_amount: parseFloat(loanData.principal || 0),
          interest: parseFloat(loanData.interest || 0),
          tenure: parseInt(loanData.tenure || 0),
          loan_number: "PREV_" + Date.now(),
          loanStatus: "1",
          role: userRole || "preview",
          date: loanData.date.toISOString ? loanData.date.toISOString() : loanData.date,
          loanType: "open",
          refreshprincipleamount: parseFloat(loanData.principal || 0),
          refreshinterest: 0,
          deduction: parseFloat(loanData.deduction || 0)
        },
        collections: collections.map(c => ({
          date: c.date.toISOString ? c.date.toISOString() : c.date,
          amount: parseFloat(c.amount || 0),
          type: c.type
        })),
        role: userRole || "preview"
      };

      const res = await fetch(`${API_BASE_URL}/preview_import`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        const statements = await res.json();
        const collectionsWithMatches = [...collections].map((c, i) => ({ ...c, originalIndex: i }));
        const mappedStmts = statements.map(stmt => {
          if (stmt.transactiontype === "newLoan") return stmt;
          const stmtDateStr = new Date(stmt.date).toISOString().split('T')[0];
          const match = collectionsWithMatches.find(c => 
            !c.matched && 
            new Date(c.date).toISOString().split('T')[0] === stmtDateStr && 
            parseFloat(c.amount || 0) === parseFloat(stmt.amountpaid || 0)
          );
          if (match) {
            match.matched = true;
            return { ...stmt, originalIndex: match.originalIndex };
          }
          return stmt;
        });
        setPreviewData(mappedStmts);
      }
    } catch (err) {
      console.error("Failed to fetch preview", err);
    } finally {
      setPreviewLoading(false);
    }
  };

  useEffect(() => {
    if (step === 3) {
      fetchPreview();
    }
  }, [step, collections, loanData.principal, loanData.interest, loanData.date]);

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    try {
      let user_id = selectedCustomer?.user_id;
      
      if (!selectedCustomer) {
        const rolePrefixMap = { Admin: "AD", User1: "SAN", User2: "SWA" };
        const prefix = rolePrefixMap[userRole === "Admin" ? userType : userRole] || "HIS";
        const samePrefixIds = customers
          .filter(c => c.user_id && c.user_id.startsWith(prefix))
          .map(c => {
            const numPart = parseInt(c.user_id.replace(prefix, ""));
            return isNaN(numPart) ? 0 : numPart;
          });
        const nextId = samePrefixIds.length > 0 ? Math.max(...samePrefixIds) + 1 : 1;
        user_id = `${prefix}${nextId}`;
      }

      const payload = {
        customerType,
        customerData: customerType === "new" ? { ...customerData, user_id } : null,
        selectedCustomerId: customerType === "existing" ? selectedCustomer?.customerid : null,
        loanData: {
          particulars: loanItems.map(i => `${i.name}(${i.quantity})`).join(","),
          number_of_items: loanItems.reduce((acc, i) => acc + i.quantity, 0).toString(),
          weight: parseFloat(loanData.weight || 0),
          net_weight: parseFloat(loanData.weight || 0) - parseFloat(loanData.deduction || 0),
          principle_amount: parseFloat(loanData.principal || 0),
          interest: parseFloat(loanData.interest || 0),
          tenure: parseInt(loanData.tenure || 0),
          loan_number: loanData.loanNumber,
          loanStatus: "1",
          role: userRole,
          date: loanData.date.toISOString ? loanData.date.toISOString() : loanData.date,
          loanType: "open",
          refreshprincipleamount: parseFloat(loanData.principal || 0),
          refreshinterest: 0,
          deduction: parseFloat(loanData.deduction || 0)
        },
        collections: collections.map(c => ({
          date: c.date.toISOString ? c.date.toISOString() : c.date,
          amount: parseFloat(c.amount || 0),
          type: c.type
        })),
        role: userRole
      };

      const res = await fetch(`${API_BASE_URL}/import_history`, {
        method: "POST",
        headers: API_HEADERS_JSON,
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to import history.");
      }

      setSuccess(true);
    } catch (err) {
      console.error("Import Error:", err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="history-success">
        <FiCheckCircle size={64} color="#10b981" />
        <h2>History Backfilled Successfully!</h2>
        <p>The past customer and their loan history have been recorded.</p>
        <button className="btn-submit" onClick={() => navigate("/admin")}>Back to Dashboard</button>
      </div>
    );
  }

  return (
    <div className="history-container">
      <div className={`history-card ${step === 3 ? "wide-card" : ""}`}>
        <div className="history-header">
          <button className="btn-back" onClick={() => step > 1 ? setStep(step - 1) : navigate(-1)}>
            <FiArrowLeft />
          </button>
          <h1>History Import</h1>
          <div className="step-indicator">Step {step} of 3</div>
        </div>

        {step === 1 && (
          <div className="step-content">
            <h3>Customer Details</h3>
            
            <div className="form-group">
              <label>Import For</label>
              <CustomSelect 
                value={customerType}
                onChange={val => {
                  setCustomerType(val);
                  setSelectedCustomer(null);
                }}
                options={[
                  { label: "New Customer", value: "new" },
                  { label: "Existing Customer", value: "existing" }
                ]}
                placeholder="Select Option"
              />
            </div>

            {customerType && (
              <>
                {customerType === "existing" ? (
                  <div className="form-group relative-group">
                    <label>SEARCH EXISTING CUSTOMER</label>
                    <div className="input-with-icon">
                      <FiSearch className="input-icon" />
                      <input 
                        type="text" 
                        placeholder="Search by Name, Phone or ID..." 
                        value={searchQuery} 
                        onChange={e => setSearchQuery(e.target.value)}
                      />
                    </div>
                    {filteredCustomers.length > 0 && (
                      <div className="search-results">
                        {filteredCustomers.map(c => (
                          <div key={c.customerid} className="search-item" onClick={() => {
                            setSelectedCustomer(c);
                            setSearchQuery("");
                          }}>
                            <FiUser /> <strong>{c.customername}</strong> ({c.user_id}) - {c.phone}
                          </div>
                        ))}
                      </div>
                    )}

                    {selectedCustomer && (
                      <div className="selected-customer-pill">
                        <div className="pill-info">
                          <FiUser /> <strong>{selectedCustomer.customername}</strong> ({selectedCustomer.user_id})
                        </div>
                        <button className="btn-clear" onClick={() => setSelectedCustomer(null)}><FiTrash2 /></button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="new-customer-fields">
                    <div className="form-group">
                      <label>NAME</label>
                      <div className="input-with-icon">
                        <FiUser className="input-icon" />
                        <input type="text" placeholder="Enter customer name" value={customerData.customerName} onChange={e => setCustomerData({...customerData, customerName: e.target.value})} />
                      </div>
                    </div>
                    <div className="form-group">
                      <label>PHONE NUMBER</label>
                      <div className="input-with-icon">
                        <FiPhone className="input-icon" />
                        <input type="text" placeholder="10-digit mobile number" value={customerData.phone} onChange={e => setCustomerData({...customerData, phone: e.target.value})} />
                      </div>
                    </div>
                    <div className="form-group">
                      <label>ADDRESS</label>
                      <div className="input-with-icon">
                        <FiMapPin className="input-icon" />
                        <textarea placeholder="Enter customer address" value={customerData.address} onChange={e => setCustomerData({...customerData, address: e.target.value})} />
                      </div>
                    </div>
                  </div>
                )}
                
                <button 
                  className="btn-next" 
                  onClick={() => setStep(2)} 
                  disabled={(customerType === "existing" && !selectedCustomer) || (customerType === "new" && (!customerData.customerName || !customerData.phone))}
                >
                  Next: Loan Details
                </button>
              </>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="step-content">
            <h3>Historical Loan Details</h3>
            <div className="form-grid">
              <div className="form-group">
                <label>Principal</label>
                <input type="number" placeholder="Principal Amount" value={loanData.principal} onChange={e => setLoanData({...loanData, principal: e.target.value})} />
              </div>
              <div className="form-group">
                <label><FiCalendar /> Loan Start Date</label>
                <DatePicker selected={loanData.date} onChange={date => setLoanData({...loanData, date})} dateFormat="yyyy-MM-dd" showMonthDropdown showYearDropdown dropdownMode="select" />
              </div>
            </div>

            <div className="items-selection-card">
              <label className="form-label">Add Items</label>
              <CustomSelect 
                value=""
                onChange={val => {
                  if (val && !loanItems.find(i => i.name === val)) {
                    setLoanItems(prev => [...prev, { name: val, quantity: 1 }]);
                  }
                }}
                options={[
                  { label: "Chain", value: "Chain" },
                  { label: "Ring", value: "Ring" },
                  { label: "Bangle", value: "Bangle" },
                  { label: "Necklaces", value: "Necklaces" },
                  { label: "Earrings", value: "Earrings" },
                  { label: "Coin", value: "Coin" }
                ]}
                placeholder="-- Choose Item --"
              />

              <div className="items-list">
                {loanItems.map((item, index) => (
                  <div key={index} className="item-pill">
                    <span className="item-info">{item.name}</span>
                    <div className="item-controls">
                      <button type="button" className="btn-counter" onClick={() => updateLoanItem(item.name, -1)}>-</button>
                      <span className="item-qty">{item.quantity}</span>
                      <button type="button" className="btn-counter" onClick={() => updateLoanItem(item.name, 1)}>+</button>
                      <button type="button" className="btn-counter remove" onClick={() => setLoanItems(prev => prev.filter(i => i.name !== item.name))}>×</button>
                    </div>
                  </div>
                ))}
                {loanItems.length === 0 && <p className="empty-items-msg">No items added yet</p>}
              </div>
            </div>

            <div className="form-grid">
              <div className="form-group">
                <label>No. of Items</label>
                <input type="number" value={loanData.items} onChange={e => setLoanData({...loanData, items: e.target.value})} />
              </div>
              <div className="form-group">
                <label>Total Weight (g)</label>
                <input type="number" step="0.01" placeholder="0.00" value={loanData.weight} onChange={e => setLoanData({...loanData, weight: e.target.value})} />
              </div>
              <div className="form-group">
                <label>Deduction (g)</label>
                <input type="number" step="0.01" value={loanData.deduction} onChange={e => setLoanData({...loanData, deduction: e.target.value})} />
              </div>
              <div className="form-group">
                <label>Net Weight (g)</label>
                <input 
                  type="text" 
                  readOnly 
                  style={{ 
                    backgroundColor: "#FFF5F5", 
                    borderColor: "#FED7D7", 
                    color: "#C53030",
                    fontWeight: "700" 
                  }}
                  value={(parseFloat(loanData.weight || 0) - parseFloat(loanData.deduction || 0)).toFixed(2)} 
                />
              </div>
            </div>

            <div className="form-grid">
              <div className="form-group">
                <label>Interest Rate (%)</label>
                <input type="number" step="0.1" value={loanData.interest} onChange={e => setLoanData({...loanData, interest: e.target.value})} />
              </div>
              <div className="form-group">
                <label>Tenure (Months)</label>
                <input type="number" value={loanData.tenure} onChange={e => setLoanData({...loanData, tenure: e.target.value})} />
              </div>
            </div>
            
            <button 
              className="btn-next" 
              onClick={async () => {
                if (!loanData.principal || !loanData.weight || loanItems.length === 0) {
                  setError("Please enter Principal, Weight, and add at least one item.");
                  return;
                }
                
                if (!loanData.loanNumber) {
                  try {
                    let userId = selectedCustomer?.user_id;
                    if (customerType === "new") {
                      const rolePrefixMap = { Admin: "AD", User1: "SAN", User2: "SWA" };
                      const prefix = rolePrefixMap[userRole === "Admin" ? userType : userRole] || "HIS";
                      const samePrefixIds = customers
                        .filter(c => c.user_id && c.user_id.startsWith(prefix))
                        .map(c => {
                          const numPart = parseInt(c.user_id.replace(prefix, ""));
                          return isNaN(numPart) ? 0 : numPart;
                        });
                      const nextId = samePrefixIds.length > 0 ? Math.max(...samePrefixIds) + 1 : 1;
                      userId = `${prefix}${nextId}`;
                    }

                    const res = await fetch(`${API_BASE_URL}/loan_data`, { headers: API_HEADERS });
                    if (res.ok) {
                        const existingLoans = await res.json();
                        const customerLoans = existingLoans.filter(l => l.customerid === (selectedCustomer ? selectedCustomer.customerid : -1));
                        
                        const prefix = userId ? userId.replace(/FIN/g, "").replace(/-/g, "") : "HIS";
                        
                        if (customerType === "new" || customerLoans.length === 0) {
                          setLoanData(prev => ({...prev, loanNumber: `${prefix}L1`}));
                        } else {
                          const indices = customerLoans.map(l => {
                            if (!l.loan_number) return 0;
                            const parts = l.loan_number.split('L');
                            const lastPart = parts[parts.length - 1];
                            const num = parseInt(lastPart);
                            return isNaN(num) ? 0 : num;
                          });
                          const nextLoanIndex = indices.length > 0 ? Math.max(...indices) + 1 : 1;
                          setLoanData(prev => ({...prev, loanNumber: `${prefix}L${nextLoanIndex}`}));
                        }
                    }
                  } catch (e) {
                      console.error("Failed to generate loan ID", e);
                      setLoanData(prev => ({...prev, loanNumber: `HIS-${Date.now().toString().slice(-5)}`}));
                  }
                }
                
                setError("");
                setStep(3);
              }}
            >
              Next: Collection History
            </button>
            {error && <div className="error-message" style={{ marginTop: '10px' }}>{error}</div>}
          </div>
        )}

        {step === 3 && (
          <div className="step-content">
            <div className="history-loan-banner">
              <div className="history-loan-header">
                <div className="hl-profile">
                  <div className="hl-avatar">
                    <FiUser size={22} />
                  </div>
                  <div>
                    <div className="hl-label">Borrower Name</div>
                    <div className="hl-value-large">
                      {customerType === "new" ? customerData.customerName || "New Customer" : selectedCustomer?.customername || "Selected Customer"}
                    </div>
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div className="hl-label"><FiHash size={12} style={{marginRight:'4px', color:'var(--primary)'}} /> Loan No. / Date</div>
                  <div className="hl-value-large" style={{ color: "var(--primary)" }}>
                    <span style={{ fontWeight: 900 }}>{loanData.loanNumber || "Auto-Gen"}</span> 
                    <span style={{ color: '#cbd5e1', margin: '0 8px', fontWeight: 400 }}>•</span> 
                    {new Date(loanData.date).toLocaleDateString("en-IN", {day:'2-digit', month:'short', year:'numeric'})}
                  </div>
                </div>
              </div>

              <div className="hl-grid">
                <div className="hl-item">
                  <div className="hl-label"><FiZap /> Principal</div>
                  <div className="hl-value">₹{parseFloat(loanData.principal || 0).toLocaleString("en-IN")}</div>
                </div>
                <div className="hl-item">
                  <div className="hl-label"><FiTarget /> Gross / Net Wt</div>
                  <div className="hl-value">{loanData.weight || 0}g / {(parseFloat(loanData.weight || 0) - parseFloat(loanData.deduction || 0)).toFixed(2)}g</div>
                </div>
                <div className="hl-item">
                  <div className="hl-label"><FiPercent /> Interest Rate</div>
                  <div className="hl-value">{loanData.interest}% PM</div>
                </div>
                <div className="hl-item">
                  <div className="hl-label"><FiClock /> Tenure</div>
                  <div className="hl-value">{loanData.tenure} Months</div>
                </div>
                <div className="hl-item">
                  <div className="hl-label"><FiFileText /> Particulars</div>
                  <div className="hl-value" style={{ fontWeight: 600 }}>
                    {loanItems.length > 0 ? loanItems.map(i => `${i.name}(${i.quantity})`).join(", ") : "N/A"}
                  </div>
                </div>
                <div className="hl-item highlight">
                  <div className="hl-label"><FiCalendar /> Next Compounding</div>
                  <div className="hl-value">{getNextCompoundDate().toLocaleDateString("en-IN", {day:'2-digit', month:'short', year:'numeric'})}</div>
                </div>
              </div>
            </div>

            <div className="entry-section">
              <h3>Add Historical Event</h3>
              <div className="entry-bar">
                <div className="input-group">
                  <label>Date</label>
                  <DatePicker 
                    selected={newEntry.date} 
                    onChange={date => setNewEntry({...newEntry, date})} 
                    dateFormat="yyyy-MM-dd"
                    showMonthDropdown
                    showYearDropdown
                    dropdownMode="select"
                  />
                </div>
                <div className="input-group">
                  <label>Type</label>
                  <CustomSelect 
                    value={newEntry.type}
                    onChange={val => setNewEntry({...newEntry, type: val})}
                    options={[
                      { label: "Payment", value: "addColl" },
                      { label: "Add Principal", value: "disbursement" }
                    ]}
                  />
                </div>
                <div className="input-group">
                  <label>Amount</label>
                  <input 
                    type="number" 
                    placeholder="0.00" 
                    value={newEntry.amount} 
                    onChange={e => setNewEntry({...newEntry, amount: e.target.value})}
                    onKeyDown={e => e.key === 'Enter' ? addOneEntry() : null}
                  />
                </div>
                <button className="btn-add-entry" onClick={addOneEntry} title="Add to Statement">
                  <FiPlus /> Add
                </button>
              </div>
            </div>


            <div className="statement-preview-section">
              <div className="statement-header">
                <h3>Live Statement Preview {previewLoading && <small style={{marginLeft: '10px', color: '#64748b'}}>Calculating...</small>}</h3>
                <button className="btn-sort" onClick={sortCollections} title="Sort Chronologically">
                   <IoIosRefresh /> Sort by Date
                </button>
              </div>
              
              <StatementTable 
                statementData={previewData} 
                onRemove={(idx) => removeCollection(idx)}
                previewMode={true}
              />
            </div>

            <button className="btn-submit" onClick={handleSubmit} disabled={loading || collections.length === 0}>
              {loading ? "Processing..." : <><FiSend /> Finalize History Import</>}
            </button>
            {error && <div className="error-message">{error}</div>}
          </div>
        )}
      </div>
    </div>
  );
};

export default History;
