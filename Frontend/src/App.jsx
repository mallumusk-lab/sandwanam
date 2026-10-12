import React, { Suspense, lazy } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import "./App.css";
import { Navbar } from "./components/Navbar";

// Lazy load components
const Login = lazy(() => import("./components/Login/Login"));
const AdminPage = lazy(() => import("./components/Admin/AdminPage"));
const NewCustomer = lazy(() => import("./components/NewCustomer/NewCustomer"));
const Analytics = lazy(() => import("./components/Analytics/Analytics"));
const UserList = lazy(() => import("./components/User/UserList"));
const NewLoan = lazy(() => import("./components/NewLoan/NewLoan"));
const LoanStatus = lazy(() => import("./components/LoanStatus/LoanStatus"));
const LoanMain = lazy(() => import("./components/LoanStatus/LoanMain"));
const StatementMain = lazy(() => import("./components/Statement/StatementMain"));
const Calculator = lazy(() => import("./components/EmiCalculator/Calculator"));
const Report = lazy(() => import("./components/Report/Report"));
const Form1 = lazy(() => import("./components/Form1/Form1"));
const History = lazy(() => import("./components/History/History"));
const BackupPage = lazy(() => import("./components/Backup/BackupPage"));
const SuperAdminLogin = lazy(() => import("./components/SuperAdmin/SuperAdminLogin"));
const SuperAdminDashboard = lazy(() => import("./components/SuperAdmin/SuperAdminDashboard"));

// Keep some small or critical components static if needed, 
// but most pages should be lazy loaded for better performance.
import { Contact, Services } from "./components/pages";
import UserPage from "./components/User/UserPage";
import Profile from './components/LoanStatus/Profile';
import Print from "./components/Print/Print";
import CalculatorPrint from "./components/EmiCalculator/CalculatorPrint";
import Form1print from './components/Form1/Form1print';
import ModifyPrint from "./components/Print/ModifyPrint";
import EditPrint from "./components/Print/EditPrint";
import AddCollectionPrint from "./components/Print/AddCollectionPrint";

function App() {
  const location = useLocation();

  // Function to determine whether to render Navbar based on path
  const renderNavbar = () => {
    if (location.pathname === "/" || location.pathname.startsWith("/superadmin")) {
      return null;
    }
    return <Navbar />;
  };

  return (
    <div className="App">
      {renderNavbar()} {/* Render Navbar conditionally */}
      <Suspense fallback={<div className="loading-screen">Loading...</div>}>
        <Routes>
          {/* <Route path="/" element={<Home />} /> */}
          <Route path="/" element={<Login />} />
          <Route path="/services" element={<Services />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/newcustomer" element={<NewCustomer />} />
          <Route path="/userpage" element={<UserPage />} />
          <Route path="/userlist" element={<UserList />} />
          <Route path="/newloan" element={<NewLoan />} />
          <Route path="/loanstatus" element={<LoanStatus />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/loanmain" element={<LoanMain />} />
          <Route path="/statement" element={<StatementMain />} />
          <Route path="/calculator" element={<Calculator />} />
          <Route path="/print" element={<Print />} />
          <Route path="/printcalculator" element={<CalculatorPrint />} />
          <Route path="/report" element={<Report />} />
          <Route path="/form1" element={<Form1 />} />
          <Route path="/form1print" element={<Form1print />} />
          <Route path="/modifyprint" element={<ModifyPrint />} />
          <Route path="/editloan" element={<EditPrint />} />
          <Route path="/adddcollection" element={<AddCollectionPrint/>} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/history" element={<History />} />
          <Route path="/backup" element={<BackupPage />} />
          <Route path="/superadmin" element={<SuperAdminLogin />} />
          <Route path="/superadmin/dashboard" element={<SuperAdminDashboard />} />
        </Routes>
      </Suspense>
    </div>
  );
}

export default App;
