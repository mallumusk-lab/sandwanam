// eslint-disable-next-line no-unused-vars
import React from 'react'

import { FaCalculator, FaFile, FaSearch, FaUserPlus } from 'react-icons/fa'
import { Link } from 'react-router-dom'

const UserPage = () => {
  return (
    <div>

      <h2>User</h2>
      <div className="centered-container">
        <Link to="/newcustomer" className="icon-link">
          <FaUserPlus color="white" className="icon" size={200} style={{ marginRight: 50, backgroundColor: "var(--primary)", padding: 20, borderRadius: "24px" }} />
        </Link>
        <FaSearch color="white" className="icon" size={200} style={{ marginRight: 50, backgroundColor: "var(--primary)", padding: 20, borderRadius: "24px" }} />
        <FaCalculator color="white" className="icon" size={200} style={{ marginRight: 50, backgroundColor: "var(--primary)", padding: 20, borderRadius: "24px" }} />
        <FaFile color="white" className="icon" size={200} style={{ marginRight: 50, backgroundColor: "var(--primary)", padding: 20, borderRadius: "24px" }} />
      </div>
    </div>
  )
}

export default UserPage

