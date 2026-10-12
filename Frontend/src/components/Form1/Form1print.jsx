
import React, { useRef, useState } from "react";
import { useReactToPrint } from "react-to-print";
import { FiPrinter } from "react-icons/fi";
import "../Print/Print.css";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faScissors } from "@fortawesome/free-solid-svg-icons";
import { useLocation, useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";

const Logo1 = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    <img src="https://i.postimg.cc/1XXXQfKn/logo1.png" alt="Logo" style={{ width: "40px", height: "40px" }} />
  </div>
);

const Logo2 = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    <img src="https://i.postimg.cc/CLZ5rn19/logo2.png" alt="Logo" style={{ width: "40px", height: "40px" }} />
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

const Form1print = () => {
  const navigate = useNavigate();
  const userType = useSelector((state) => state.myfin.user);
  const userRole = useSelector((state) => state.myfin.data);
  const { search } = useLocation();
  const queryParams = new URLSearchParams(search);
  const inputNumbers = Array.from({ length: 33 }, (_, index) =>
    queryParams.get(`inputNumber${index + 1}`)
  );

  const componentRef1 = useRef();
  const componentRef2 = useRef();
  const componentRef3 = useRef();

  const handlePrint1 = useReactToPrint({ content: () => componentRef1.current });
  const handlePrint2 = useReactToPrint({ content: () => componentRef2.current });
  const handlePrint3 = useReactToPrint({ content: () => componentRef3.current });

  const currentDate = new Date();
  const formattedDate = `${currentDate.getDate()}/${currentDate.getMonth() + 1}/${currentDate.getFullYear()}`;

  let userInfo;
  if (userRole === "Admin") {
    userInfo = userType === "User1" ? User1Info : User2Info;
  } else {
    userInfo = userRole === "User1" ? User1Info : User2Info;
  }

  const PageHeader = ({ title }) => (
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
      <div className="doc-title-container" style={{ marginTop: '25px' }}>
        <h2 className="doc-title">{title}</h2>
        <div className="doc-date">Date: {formattedDate}</div>
      </div>
    </div>
  );

  return (
    <div className="print-page-wrapper">
      <div className="no-print print-actions">
        <button onClick={() => navigate(-1)} className="btn-back">
          Back
        </button>
        <button onClick={handlePrint1} className="btn-print">
          <FiPrinter /> Application
        </button>
        <button onClick={handlePrint2} className="btn-print">
          <FiPrinter /> Receipt 1
        </button>
        <button onClick={handlePrint3} className="btn-print">
          <FiPrinter /> Receipt 2
        </button>
      </div>

      <div className="print-container">
        {/* FORM 1 - CONTENT 1 */}
        <div ref={componentRef1} className="receipt-card">
          <PageHeader title="Loan Application Form" />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px' }}>
            <table className="form-table">
              <tbody>
                <tr><td>അപേക്ഷകയുടെ പേര്</td><td><span className="input_value">{inputNumbers[0]}</span></td></tr>
                <tr><td>ജനനം/വയസ്</td><td><span className="input_value">{inputNumbers[1]}</span></td></tr>
                <tr><td>ആധാർ നമ്പർ</td><td><span className="input_value">{inputNumbers[2]}</span></td></tr>
                <tr><td>ID കാർഡ് നമ്പർ</td><td><span className="input_value">{inputNumbers[3]}</span></td></tr>
                <tr><td>മോബൈൽ നമ്പർ</td><td><span className="input_value">{inputNumbers[4]}</span></td></tr>
                <tr><td>മേൽവിലാസം</td><td><span className="input_value">{inputNumbers[5]}</span></td></tr>
              </tbody>
            </table>
            <table className="form-table">
              <tbody>
                <tr><td>ഭർത്താവിൻ്റെ പേര്</td><td><span className="input_value">{inputNumbers[6]}</span></td></tr>
                <tr><td>ജനനം/വയസ്</td><td><span className="input_value">{inputNumbers[7]}</span></td></tr>
                <tr><td>ആധാർ നമ്പർ</td><td><span className="input_value">{inputNumbers[8]}</span></td></tr>
                <tr><td>ID കാർഡ് നമ്പർ</td><td><span className="input_value">{inputNumbers[9]}</span></td></tr>
                <tr><td>മോബൈൽ നമ്പർ</td><td><span className="input_value">{inputNumbers[10]}</span></td></tr>
                <tr><td>മേൽവിലാസം</td><td><span className="input_value">{inputNumbers[11]}</span></td></tr>
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: '30px', borderTop: '1px solid #e5e7eb', paddingTop: '25px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: '800', textAlign: 'center', marginBottom: '20px', color: 'var(--print-primary)' }}>വായ്‌പ വിവരങ്ങൾ</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px' }}>
              <table className="form-table">
                <tbody>
                  <tr><td>അപേക്ഷകയുടെ പേര്</td><td><span className="input_value">{inputNumbers[12]}</span></td></tr>
                  <tr><td>മകൾ / മകൻ പേര്</td><td><span className="input_value">{inputNumbers[13]}</span></td></tr>
                  <tr><td>ആധാർ നമ്പർ</td><td><span className="input_value">{inputNumbers[14]}</span></td></tr>
                  <tr><td>ഗ്രൂപ്പിൻ്റെ പേര്</td><td><span className="input_value">{inputNumbers[15]}</span></td></tr>
                  <tr><td>ഗ്രൂപ്പ് നമ്പർ</td><td><span className="input_value">{inputNumbers[16]}</span></td></tr>
                  <tr><td>കസ്റ്റമർ നമ്പർ</td><td><span className="input_value">{inputNumbers[17]}</span></td></tr>
                </tbody>
              </table>
              <table className="form-table">
                <tbody>
                  <tr><td>ഭർത്താവിൻ്റെ പേര്</td><td><span className="input_value">{inputNumbers[20]}</span></td></tr>
                  <tr><td>റേഷൻ കാർഡ് നമ്പർ</td><td><span className="input_value">{inputNumbers[21]}</span></td></tr>
                  <tr><td>വായ്‌പ ആവശ്യം</td><td><span className="input_value">{inputNumbers[22]}</span></td></tr>
                  <tr><td>ലോൺ വ്യവസ്ഥ</td><td><span className="input_value">{inputNumbers[23]}</span></td></tr>
                  <tr><td>വായ്‌പ കാലാവധി</td><td><span className="input_value">{inputNumbers[26]}</span></td></tr>
                  <tr><td>തിരിച്ചടവ് തുക</td><td><span className="input_value">{inputNumbers[27]}</span></td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="summary-box" style={{ marginTop: '35px' }}>
            <p className="malayalam-text" style={{ textAlign: 'center', fontWeight: '800', fontSize: '16px', marginBottom: '15px', color: 'var(--print-primary)' }}>ശുപാർശ</p>
            <p className="malayalam-text">
              തിയതികളിൽ നടന്ന ഗ്രൂപ്പ് യോഗത്തിൻ്റെയും വായ്‌പ കരാറിലെ മറ്റു അംഗങ്ങളുടെയും സമ്മതപ്രകാരം ശ്രീമതി {inputNumbers[0]} ക്ക് വായ്‌പ നൽകുവാൻ സെൻ്റർ അധികാരികൾ എന്ന നിലയിൽ ഞങ്ങൾ അധികാരം നൽകുന്നു. 
              പ്രസ്‌തുത വ്യക്തി എന്തെങ്കിലും കാരണവശാൽ വായ്‌പ തവണ തുകകൾ തിരിച്ച് അടയ്ക്കാത്ത പക്ഷം സെൻ്ററിലെ എല്ലാ അംഗങ്ങളും ചേർന്ന് വായ്‌പ തിരിച്ചടയ്ക്കാൻ പ്രോത്സാഹിപ്പിച്ചു വായ്‌പ അടപ്പിക്കും. 
              അല്ലെങ്കിൽ ഗ്രൂപ്പ് ഉത്തരവാദിത്വത്തിൽ ഞങ്ങൾ എല്ലാവരും ചേർന്ന് വായ്‌പ തിരിച്ചടയ്ക്കുമെന്ന് ഇതിനാൽ ഉറപ്പു തരുന്നു.
            </p>
            <div className="signature-row">
              <div className="sig-box">പ്രസിഡന്റ്</div>
              <div className="sig-box">സെക്രട്ടറി</div>
              <div className="sig-box">ഗ്രൂപ്പ് ലീഡർ</div>
              <div className="sig-box">ഗ്രൂപ്പ് അംഗം</div>
            </div>
          </div>
        </div>

        {/* RECEIPT 1 - OFFICE COPY */}
        <div ref={componentRef2} className="receipt-card">
          <PageHeader title="Office Copy" />
          <div className="info-grid">
            <div className="info-item"><span className="info-label">Name</span><span className="info-value">{inputNumbers[0]}</span></div>
            <div className="info-item"><span className="info-label">Phone Number</span><span className="info-value">{inputNumbers[4]}</span></div>
            <div className="info-item"><span className="info-label">Address</span><span className="info-value">{inputNumbers[5]}</span></div>
            <div className="info-item"><span className="info-label">Principal Amount</span><span className="info-value">₹{inputNumbers[18]}</span></div>
            <div className="info-item"><span className="info-label">EMI</span><span className="info-value">₹{inputNumbers[19]}</span></div>
            <div className="info-item"><span className="info-label">Tenure</span><span className="info-value">{inputNumbers[26]} Months</span></div>
          </div>
          <div className="receipt-footer">
            <div className="footer-seal">Office Seal</div>
            <div className="footer-signature"><div className="sig-line">Authorized Signatory</div></div>
          </div>
        </div>

        <div className="cut-line no-print">
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
          <hr />
          <FontAwesomeIcon icon={faScissors} className="cut-line-icon" />
        </div>

        {/* RECEIPT 2 - CUSTOMER COPY */}
        <div ref={componentRef3} className="receipt-card">
          <PageHeader title="Customer Copy" />
          <div className="info-grid">
            <div className="info-item"><span className="info-label">Name</span><span className="info-value">{inputNumbers[0]}</span></div>
            <div className="info-item"><span className="info-label">Phone Number</span><span className="info-value">{inputNumbers[4]}</span></div>
            <div className="info-item"><span className="info-label">Address</span><span className="info-value">{inputNumbers[5]}</span></div>
            <div className="info-item"><span className="info-label">Principal Amount</span><span className="info-value">₹{inputNumbers[18]}</span></div>
            <div className="info-item"><span className="info-label">EMI</span><span className="info-value">₹{inputNumbers[19]}</span></div>
            <div className="info-item"><span className="info-label">Tenure</span><span className="info-value">{inputNumbers[26]} Months</span></div>
          </div>
          <div className="receipt-footer">
            <div className="footer-seal">Office Seal</div>
            <div className="footer-signature"><div className="sig-line">Authorized Signatory</div></div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Form1print;
