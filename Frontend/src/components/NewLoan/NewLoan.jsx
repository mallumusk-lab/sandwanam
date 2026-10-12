import { useState, useEffect } from "react";
import { format } from "date-fns";
import DatePicker from "react-datepicker"; 
import "react-datepicker/dist/react-datepicker.css"; 
import { useNavigate } from "react-router-dom";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import { Myaction } from "../../store/MyfinSlice";
import { useDispatch } from "react-redux";
import { useSelector } from "react-redux";

const NewLoan = () => {
  const userRole = useSelector((state) => state.myfin.data);
  const userType = useSelector((state) => state.myfin.user);
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const customerid = queryParams.get("customerid");
  const dispatch = useDispatch();
  const [formData, setFormData] = useState({
    particulars: "",
    numberOfItems: "",
    weight: "",
    netWeight: "", // This will now represent the deduction amount conceptually in the UI
    principleAmount: "",
    interest: "",
    tenure: "",
    currentDate: new Date(), 
  });

  const [submitting, setSubmitting] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [items, setItems] = useState([]); // Dynamic list for multiple particulars
  const [existingLoans, setExistingLoans] = useState([]);
  const [customerData, setCustomerData] = useState(null);

  useEffect(() => {
    const fetchExistingLoans = async () => {
      try {
        const responseData = await fetch(`${API_BASE_URL}/loan_data`, {
          method: "GET",
          headers: API_HEADERS,
        });
        if (responseData.ok) {
          const existingLoansData = await responseData.json();
          setExistingLoans(existingLoansData);
        }

        const responseCustomer = await fetch(`${API_BASE_URL}/customers/${customerid}`, {
          method: "GET",
          headers: API_HEADERS,
        });
        if (responseCustomer.ok) {
          const cust = await responseCustomer.json();
          setCustomerData(cust);
        }
      } catch (error) {
        console.error("Error fetching data:", error);
      }
    };

    fetchExistingLoans();
  }, []);

  const calculateNextLoanNumber = () => {
    if (!customerData || !existingLoans) return "";
    
    // Filter loans for this specific customer
    const customerLoans = existingLoans.filter(l => l.customerid === parseInt(customerid));
    
    // Find the max index used so far for this customer
    const indices = customerLoans.map(l => {
      if (!l.loan_number) return 0;
      const parts = l.loan_number.split('L');
      const lastPart = parts[parts.length - 1];
      const num = parseInt(lastPart);
      return isNaN(num) ? 0 : num;
    });

    const nextLoanIndex = indices.length > 0 ? Math.max(...indices) + 1 : 1;
    
    // Remove "FIN" and any hyphens just in case
    const cleanUserId = customerData.user_id.replace(/FIN/g, "").replace(/-/g, "");
    return `${cleanUserId}L${nextLoanIndex}`;
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    if (name === "particulars" && value !== "") {
      // Add new item to the list if not already there
      const exists = items.find(i => i.name === value);
      if (!exists) {
        setItems(prev => [...prev, { name: value, quantity: 1 }]);
      }
      return;
    }
    setFormData((prevData) => ({ ...prevData, [name]: value }));
  };

  const updateItemQuantity = (name, amount) => {
    setItems(prev => prev.map(item => {
      if (item.name === name) {
        const newQty = Math.max(0, item.quantity + amount);
        return { ...item, quantity: newQty };
      }
      return item;
    }).filter(item => item.quantity > 0)); // Remove items with 0 quantity
  };

  const handleDateChange = (date) => {
    setFormData((prevData) => ({ ...prevData, currentDate: date }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
  
    if (submitting) return;
    setSubmitting(true);

    // Validation checks
    if (
      items.length === 0 ||
      !formData.weight ||
      !formData.netWeight ||
      !formData.principleAmount ||
      !formData.interest ||
      !formData.tenure
    ) {
      alert("All fields are required, including at least one item");
      return;
    }

    const numericRegex = /^[0-9]+(\.[0-9]+)?$/;
    const decimalRegex = /^[0-9]+(\.[0-9]*)?$/;

    if (!numericRegex.test(formData.weight)) {
      alert("Weight must be numeric");
      return;
    }

    if (!numericRegex.test(formData.netWeight)) {
      alert("Deduction must be numeric");
      return;
    }

    if (!decimalRegex.test(formData.principleAmount)) {
      alert("Principle Amount must be a valid number");
      return;
    }

    if (!decimalRegex.test(formData.interest)) {
      alert("Interest must be a valid number");
      return;
    }

    if (!numericRegex.test(formData.tenure)) {
      alert("Tenure must be numeric");
      return;
    }

    try {
      const currentDate = formData.currentDate.toISOString();
      const deductionAmount = parseFloat(formData.netWeight);
      const weightAmount = parseFloat(formData.weight);
      const net_weight = weightAmount - deductionAmount;

      // Serialize dynamic items
      const serialParticulars = items.map(i => `${i.name}(${i.quantity})`).join(",");
      const totalItems = items.reduce((acc, i) => acc + i.quantity, 0);

      const response = await fetch(`${API_BASE_URL}/loan_data`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": "12345",
        },
        body: JSON.stringify({
          customerId: parseInt(customerid),
          particulars: serialParticulars,
          number_of_items: totalItems.toString(),
          weight: formData.weight,
          net_weight: net_weight.toString(),
          principle_amount: formData.principleAmount,
          interest: formData.interest,
          tenure: parseInt(formData.tenure),
          loan_number: calculateNextLoanNumber(),
          loanStatus: "1",
          role: "Admin",
          date: currentDate,
          loanType: "open",
          refreshprincipleamount: formData.principleAmount.toString(),
          refreshinterest: "0",
          deduction: formData.netWeight,
        }),
      });
  
      if (response.ok) {
        alert("Loan application submitted successfully!");
        navigate(`/loanmain?customerid=${customerid}&userRole=${JSON.stringify(userRole)}`);
      } else {
        const errorData = await response.json();
        alert(`Error: ${errorData.message}`);
      }
    } catch (error) {
      console.error("Error submitting loan application:", error);
      alert("Error submitting loan application. Please try again later.");
    } finally {
      setSubmitting(false);
    }
  };
  

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        background: "var(--bg-app)",
        padding: "40px 20px",
        fontFamily: "var(--font-main)",
      }}
    >
      <form
        style={{
          width: "100%",
          maxWidth: "480px",
          padding: "32px",
          background: "var(--bg-glass)",
          backdropFilter: "blur(20px)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-xl)",
          position: "relative",
          boxSizing: "border-box",
          border: "1px solid rgba(255,255,255,0.4)",
        }}
        onSubmit={handleSubmit}
      >
        <button
          type="button"
          onClick={() => navigate(-1)}
          style={{
            position: "absolute",
            top: "20px",
            right: "20px",
            width: "36px",
            height: "36px",
            borderRadius: "50%",
            backgroundColor: "var(--primary-light)",
            color: "var(--primary)",
            border: "none",
            cursor: "pointer",
            fontSize: "24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "all 0.3s ease",
            boxShadow: "0 4px 12px rgba(0,0,0,0.05)",
          }}
          onMouseEnter={(e) => {
            e.target.style.transform = "rotate(90deg)";
            e.target.style.backgroundColor = "var(--primary)";
            e.target.style.color = "white";
          }}
          onMouseLeave={(e) => {
            e.target.style.transform = "rotate(0deg)";
            e.target.style.backgroundColor = "var(--primary-light)";
            e.target.style.color = "var(--primary)";
          }}
          title="Close"
        >
          &times;
        </button>

        <h2 style={{ 
          marginBottom: "24px", 
          color: "var(--text-heading)", 
          fontFamily: "var(--font-heading)",
          fontSize: "32px",
          fontWeight: "700",
          letterSpacing: "-0.5px"
        }}>
          New Loan
        </h2>

        <div style={{ marginBottom: "20px" }}>
          <label style={labelStyle}>Date</label>
          <DatePicker
            selected={formData.currentDate}
            onChange={handleDateChange}
            dateFormat="yyyy-MM-dd"
            showMonthDropdown
            showYearDropdown
            dropdownMode="select"
            customInput={<input style={inputStyle} />}
          />
        </div>

        <div style={{ 
          marginBottom: "24px", 
          padding: "20px", 
          backgroundColor: "#F9FAFE",
          borderRadius: "16px",
          border: "1px solid #E0E7FF"
        }}>
          <label style={{ ...labelStyle, marginBottom: "12px" }}>
            Add Items
          </label>
          <select
            name="particulars"
            value=""
            onChange={handleChange}
            style={inputStyle}
          >
            <option value="">-- Choose Item --</option>
            <option value="Chain">Chain</option>
            <option value="Ring">Ring</option>
            <option value="Bangle">Bangle</option>
            <option value="Necklaces">Necklaces</option>
            <option value="Earrings">Earrings</option>
            <option value="Coin">Coin</option>
          </select>

          <div style={{ marginTop: "16px" }}>
            {items.map((item, index) => (
              <div key={index} style={{ 
                display: "flex", 
                justifyContent: "space-between", 
                alignItems: "center", 
                marginBottom: "8px", 
                padding: "12px", 
                backgroundColor: "white", 
                borderRadius: "12px", 
                boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
                border: "1px solid #F0F0F0"
              }}>
                <span style={{ fontWeight: "600", color: "#4A5568" }}>{item.name}</span>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <button type="button" onClick={() => updateItemQuantity(item.name, -1)} style={counterButtonStyle}>-</button>
                  <span style={{ width: "24px", textAlign: "center", fontWeight: "600" }}>{item.quantity}</span>
                  <button type="button" onClick={() => updateItemQuantity(item.name, 1)} style={counterButtonStyle}>+</button>
                  <button 
                    type="button" 
                    onClick={() => setItems(prev => prev.filter(i => i.name !== item.name))}
                    style={{ ...counterButtonStyle, backgroundColor: "#FED7D7", color: "#E53E3E" }}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
            {items.length === 0 && (
              <p style={{ fontSize: "14px", color: "#A0AEC0", textAlign: "center", margin: "10px 0" }}>
                No items added yet
              </p>
            )}
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: "16px", marginBottom: "16px" }}>
          <div style={{ flex: "1" }}>
            <label style={labelStyle}>Weight (g)</label>
            <input
              type="text"
              name="weight"
              value={formData.weight}
              onChange={handleChange}
              style={inputStyle}
              placeholder="0.00"
            />
          </div>

          <div style={{ flex: "1" }}>
            <label style={labelStyle}>Deduction (g)</label>
            <input
              type="text"
              name="netWeight"
              value={formData.netWeight}
              onChange={handleChange}
              style={inputStyle}
              placeholder="0.00"
            />
          </div>
        </div>

        <div style={{ 
          marginBottom: "20px",
          padding: "12px 16px",
          backgroundColor: "#FFF5F5",
          borderRadius: "12px",
          border: "1px solid #FED7D7",
          display: "inline-block"
        }}>
          <p style={{ margin: 0, color: "#C53030", fontWeight: "600", fontSize: "14px" }}>
            Net Weight: <span style={{ fontSize: "16px" }}>{formData.weight && formData.netWeight 
              ? (parseFloat(formData.weight) - parseFloat(formData.netWeight)).toFixed(2) 
              : "0.00"}</span> g
          </p>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: "16px", marginBottom: "16px" }}>
          <div style={{ flex: "1" }}>
            <label style={labelStyle}>Principal Amount</label>
            <input
              type="text"
              name="principleAmount"
              value={formData.principleAmount}
              onChange={handleChange}
              style={inputStyle}
              placeholder="0.00"
            />
          </div>

          <div style={{ flex: "1" }}>
            <label style={labelStyle}>Interest (%)</label>
            <input
              type="text"
              name="interest"
              value={formData.interest}
              onChange={handleChange}
              style={inputStyle}
              placeholder="0.00"
            />
          </div>
        </div>

        <div style={{ marginBottom: "32px" }}>
          <label style={labelStyle}>Tenure (Months)</label>
          <input
            type="text"
            name="tenure"
            value={formData.tenure}
            onChange={handleChange}
            style={inputStyle}
            placeholder="Months"
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          style={{
            width: "100%",
            backgroundColor: submitting ? "var(--text-light)" : (isHovered ? "var(--primary-hover)" : "var(--primary)"),
            color: "white",
            padding: "16px",
            border: "none",
            borderRadius: "var(--radius-md)",
            cursor: submitting ? "not-allowed" : "pointer",
            fontSize: "18px",
            fontWeight: "700",
            fontFamily: "var(--font-main)",
            transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            boxShadow: isHovered ? "var(--shadow-lg)" : "var(--shadow-md)",
            transform: isHovered ? "translateY(-2px)" : "translateY(0)",
          }}
        >
          {submitting ? "Processing..." : "Create Loan"}
        </button>
      </form>
    </div>
  );
};

const labelStyle = {
  display: "block",
  marginBottom: "8px",
  fontSize: "14px",
  fontWeight: "600",
  color: "#4A5568",
  fontFamily: "'Inter', sans-serif",
};

const inputStyle = {
  width: "100%",
  padding: "12px 16px",
  borderRadius: "12px",
  border: "2px solid #E2E8F0",
  boxSizing: "border-box",
  fontSize: "15px",
  color: "#2D3748",
  backgroundColor: "white",
  transition: "all 0.3s ease",
  outline: "none",
  fontFamily: "'Inter', sans-serif",
};

const counterButtonStyle = {
  backgroundColor: "#EDF2F7",
  color: "#4A5568",
  border: "none",
  borderRadius: "8px",
  width: "32px",
  height: "32px",
  cursor: "pointer",
  fontSize: "18px",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  transition: "all 0.2s ease",
  fontWeight: "600",
};

export default NewLoan;
