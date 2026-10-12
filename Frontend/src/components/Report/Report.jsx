import React, { useEffect, useState, useMemo } from "react";
import DatePicker from "react-datepicker";
import Table from "react-bootstrap/Table";
import "react-datepicker/dist/react-datepicker.css";
import "./Report.css";
import {  API_BASE_URL , API_HEADERS, API_HEADERS_JSON } from "../../Service/Index";
import { FaSearch, FaPrint, FaFileExport } from "react-icons/fa";

const Report = () => {
  const [rangeType, setRangeType] = useState("month");
  const [startDate, setStartDate] = useState(new Date());
  const [endDate, setEndDate] = useState(new Date());
  const [reportData, setReportData] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedLoanNumber, setSelectedLoanNumber] = useState("All");

  // Modern Currency Formatter
  const formatCurrency = (amount) => {
    if (amount === undefined || amount === null || amount === "" || amount === "-") return "-";
    const num = parseFloat(amount);
    if (isNaN(num)) return "-";
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const setDatesByRange = (type) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let start = new Date(today);
    let end = new Date(today);
    end.setHours(23, 59, 59, 999);

    if (type === "today") {
      start = new Date(today);
    } else if (type === "week") {
      const day = today.getDay();
      const diff = today.getDate() - day;
      start = new Date(today.setDate(diff));
    } else if (type === "month") {
      start = new Date(today.getFullYear(), today.getMonth(), 1);
    }

    setStartDate(start);
    setEndDate(end);
  };

  useEffect(() => {
    if (rangeType !== "custom") {
      setDatesByRange(rangeType);
    }
  }, [rangeType]);

  const fetchData = async () => {
    if (!startDate || !endDate) return;
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/statement`, {
        headers: API_HEADERS,
      });

      if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

      const allData = await response.json();

      const dateFormat = (date) => {
        const d = new Date(date);
        return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")}`;
      };

      const startStr = dateFormat(startDate);
      const endStr = dateFormat(endDate);

      let filtered = allData.filter((item) => {
        const itemDate = item.date.split("T")[0];
        return itemDate >= startStr && itemDate <= endStr;
      });

      if (selectedLoanNumber !== "All") {
        filtered = filtered.filter((item) => item.loan_number.startsWith(selectedLoanNumber));
      }

      setReportData(filtered);
    } catch (error) {
      console.error("Error fetching report data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [startDate, endDate, selectedLoanNumber]);

  const filteredReportData = useMemo(() => {
    return reportData.filter((item) => {
      const search = searchTerm.toLowerCase();
      return (
        item.loan_number.toLowerCase().includes(search) ||
        (item.description && item.description.toLowerCase().includes(search)) ||
        (item.particulars && item.particulars.toLowerCase().includes(search))
      );
    });
  }, [reportData, searchTerm]);

  const { debitSum, creditSum } = useMemo(() => {
    return filteredReportData.reduce(
      (acc, item) => {
        if (item.transactiontype === "newLoan" || item.transactiontype === "disbursement") {
          acc.debitSum += parseFloat(item.principlebalance || 0);
        } else if (item.transactiontype === "modify") {
          acc.debitSum += parseFloat(item.amountpaid || 0);
        } else if (item.transactiontype === "addColl") {
          acc.creditSum += parseFloat(item.amountpaid || 0);
        }
        return acc;
      },
      { debitSum: 0, creditSum: 0 }
    );
  }, [filteredReportData]);

  const exportToCSV = () => {
    const headers = ["SL No.", "Date", "Description", "Debit", "Credit"];
    const rows = filteredReportData.map((item, index) => [
      index + 1,
      item.date,
      item.transactiontype === "newLoan" || item.transactiontype === "disbursement" ? `Loan ${item.loan_number}` : `Coll ${item.loan_number}`,
      item.transactiontype === "newLoan" || item.transactiontype === "disbursement" ? item.principlebalance : item.transactiontype === "modify" ? item.amountpaid : "",
      item.transactiontype === "addColl" ? item.amountpaid : "",
    ]);

    const csvContent = [headers, ...rows].map((e) => e.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `loan_report_${rangeType}.csv`);
    link.style.visibility = "hidden";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="report-page">
      <div className="report-header-card">
        <h1>Loan Analysis Report</h1>
        
        <div className="report-controls">
          <div className="control-group">
            <label>Range</label>
            <select value={rangeType} onChange={(e) => setRangeType(e.target.value)} className="modern-select">
              <option value="today">Today</option>
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="custom">Custom Range</option>
            </select>
          </div>

          {rangeType === "custom" && (
            <div className="date-pickers animated fade-in">
              <div className="control-group">
                <label>From</label>
                <DatePicker selected={startDate} onChange={setStartDate} className="modern-input" showMonthDropdown showYearDropdown dropdownMode="select" />
              </div>
              <div className="control-group">
                <label>To</label>
                <DatePicker selected={endDate} onChange={setEndDate} className="modern-input" showMonthDropdown showYearDropdown dropdownMode="select" />
              </div>
            </div>
          )}

          <div className="control-group">
            <label>Entity</label>
            <select value={selectedLoanNumber} onChange={(e) => setSelectedLoanNumber(e.target.value)} className="modern-select">
              <option value="All">All Entities</option>
              <option value="SAN">SAN (Santhwanam)</option>
              <option value="SWA">SWA (Swathantra)</option>
            </select>
          </div>

          <div className="search-box">
            <FaSearch className="search-icon" />
            <input
              type="text"
              placeholder="Search loan #..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="modern-input"
            />
          </div>

          <div className="action-buttons">
            <button onClick={() => window.print()} className="action-btn print">
              <FaPrint /> Print
            </button>
            <button onClick={exportToCSV} className="action-btn export">
              <FaFileExport /> Export
            </button>
          </div>
        </div>
      </div>

      <div className="report-content">
        {loading ? (
          <div className="loader">Analyzing Data...</div>
        ) : filteredReportData.length > 0 ? (
          <div className="table-responsive animated slide-up">
            <Table hover responsive className="modern-report-table">
              <thead>
                <tr>
                  <th className="col-index">#</th>
                  <th className="col-date">Date</th>
                  <th className="col-desc">Transaction Description</th>
                  <th className="col-amount">Debit (Out)</th>
                  <th className="col-amount">Credit (In)</th>
                </tr>
              </thead>
              <tbody>
                {filteredReportData.map((data, index) => (
                  <tr key={data.statementid || index} className="report-row">
                    <td className="col-index">{index + 1}</td>
                    <td className="col-date">
                      <div className="date-main">{new Date(data.date).toLocaleDateString()}</div>
                      <div className="date-sub">{new Date(data.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                    </td>
                    <td className="col-desc">
                      <div className="txn-wrapper">
                        <span className={`txn-badge ${data.transactiontype}`}>
                          {data.transactiontype === "newLoan" || data.transactiontype === "disbursement" ? "NEW LOAN" : data.transactiontype === "addColl" ? "COLLECTION" : "MODIFIED"}
                        </span>
                        <span className="loan-num">{data.loan_number}</span>
                      </div>
                    </td>
                    <td className="col-amount debit">
                      {data.transactiontype === "newLoan" || data.transactiontype === "disbursement" ? formatCurrency(data.principlebalance) : data.transactiontype === "modify" ? formatCurrency(data.amountpaid) : "-"}
                    </td>
                    <td className="col-amount credit">
                      {data.transactiontype === "addColl" ? formatCurrency(data.amountpaid) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="report-footer">
                <tr className="report-summary-row">
                  <td></td>
                  <td></td>
                  <td className="summary-label">NET TOTALS</td>
                  <td className="summary-value debit">{formatCurrency(debitSum)}</td>
                  <td className="summary-value credit">{formatCurrency(creditSum)}</td>
                </tr>
              </tfoot>
            </Table>
          </div>
        ) : (
          <div className="empty-state">
            <p>No transactions found for the selected criteria.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Report;
