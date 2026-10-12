import React, { useState, useEffect } from "react";
import "./UserList.css";
import { FiEye, FiPlusCircle, FiSearch, FiUsers } from "react-icons/fi";
import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { fetchUserData } from "../../Service/data";

const UserList = () => {
  const [data, setData] = useState([]);
  const [searchInput, setSearchInput] = useState("");
  const navigate = useNavigate();
  const [users, setUsers] = useState("");
  const userType = useSelector((state) => state.myfin.user);
  const userRole = useSelector((state) => state.myfin.data);

  useEffect(() => {
    if (userType === "User1") {
      setUsers("User1");
    } else if (userType === "User2") {
      setUsers("User2");
    }
  }, [userType]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const result = await fetchUserData();
        if (Array.isArray(result)) {
          const sortedData = [...result].sort(
            (a, b) => b.customerid - a.customerid
          );
          setData(sortedData);
        } else {
          setData([]);
        }
      } catch (error) {
        console.error("Error fetching data:", error);
      }
    };
    fetchData();
  }, []);

  const handleButtonClick = (customerid, loanStatus) => {
    switch (loanStatus) {
      case "0":
        navigate(`/newloan?customerid=${customerid}`);
        return;
      case "1":
      case "2":
        navigate(`/loanmain?customerid=${customerid}&userRole=${JSON.stringify(userRole)}`);
        break;
      default:
        console.log("Loan Status not available");
    }
  };

  const getButtonClass = (loanStatus) => {
    if (loanStatus === "0") return "btn-table-action btn-add";
    if (loanStatus === "1" || loanStatus === "2") return "btn-table-action btn-view";
    return "btn-table-action";
  };

  const filteredUserRoleData = data.filter((row) => {
    switch (userRole) {
      case "Admin": return true;
      case "User1": return row.user_id && row.user_id.startsWith("SAN");
      case "User2": return row.user_id && row.user_id.startsWith("SWA");
      default: return true;
    }
  });

  const filteredData = filteredUserRoleData
    .filter(
      (row) =>
        (row.user_id && row.user_id.toLowerCase().includes(searchInput.toLowerCase())) ||
        (row.customername && row.customername.toLowerCase().includes(searchInput.toLowerCase()))
    )
    .filter((row) => {
      if (userRole === "Admin") {
        switch (users) {
          case "User1": return row.user_id && row.user_id.startsWith("SAN");
          case "User2": return row.user_id && row.user_id.startsWith("SWA");
          default: return true;
        }
      } else {
        return true;
      }
    });

  return (
    <div className="user-list-container">
      <div className="user-list-header">
        <h2>Customer Dashboard</h2>
        <div className="search-container">
          <div className="search-wrapper">
            <FiSearch className="search-icon" />
            <input
              type="text"
              className="premium-search-input"
              placeholder="Search by ID or Customer Name..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="table-card">
        <table className="premium-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Customer ID</th>
              <th>Full Name</th>
              <th>Phone</th>
              <th>Address</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>
            {filteredData.map((row, index) => (
              <tr key={index}>
                <td style={{ color: "#94a3b8", fontWeight: 500 }}>{index + 1}</td>
                <td>
                  <span className="customer-id-tag">{row.user_id}</span>
                </td>
                <td className="customer-name">{row.customername}</td>
                <td>
                  <span className="phone-link">{row.phone}</span>
                </td>
                <td>
                  <div className="address-text" title={row.address}>
                    {row.address}
                  </div>
                </td>
                <td>
                  <button
                    className={getButtonClass(row.loanstatus)}
                    onClick={() => handleButtonClick(row.customerid, row.loanstatus)}
                  >
                    {row.loanstatus === "0" ? (
                      <><FiPlusCircle /> Add Loan</>
                    ) : (
                      <><FiEye /> View Detail</>
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredData.length === 0 && (
          <div style={{ textAlign: "center", padding: "3rem", color: "#94a3b8" }}>
            <FiUsers size={48} style={{ marginBottom: "1rem", opacity: 0.3 }} />
            <p>No customers found matching your criteria.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default UserList;
