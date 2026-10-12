
import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useSelector } from "react-redux";
import { FiPrinter } from "react-icons/fi";
import "./Form1.css";

const Form1 = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [formData, setFormData] = useState({
    inputNumber1: "",
    inputNumber2: "",
    inputNumber3: "",
    inputNumber4: "",
    inputNumber5: "",
    inputNumber6: "",
    inputNumber7: "",
    inputNumber8: "",
    inputNumber9: "",
    inputNumber10: "",
    inputNumber11: "",
    inputNumber12: "",
    inputNumber13: "",
    inputNumber14: "",
    inputNumber15: "",
    inputNumber16: "",
    inputNumber17: "",
    inputNumber18: "",
    inputNumber19: "",
    inputNumber20: "",
    inputNumber21: "",
    inputNumber22: "",
    inputNumber23: "",
    inputNumber24: "",
    inputNumber25: "",
    inputNumber26: "",
    inputNumber27: "",
    inputNumber28: "",
    inputNumber29: "",
    inputNumber30: "",
    inputNumber31: "",
    inputNumber32: "",
    inputNumber33: "",
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: value,
    });
  };

  const labels = {
    inputNumber1: "അപേക്ഷകയുടെ പേര്",
    inputNumber2: "ജനന തിയതി വയസ്",
    inputNumber3: "ആധാർ നമ്പർ",
    inputNumber4: "ID കാർഡ് നമ്പർ",
    inputNumber5: "മോബൈൽ നമ്പർ",
    inputNumber6: "മേൽവിലാസം",
    inputNumber7: "ഭർത്താവിൻ്റെ പേര്",
    inputNumber8: "ജനന തിയതി വയസ്",
    inputNumber9: "ആധാർ നമ്പർ",
    inputNumber10: "ID കാർഡ് നമ്പർ",
    inputNumber11: "മോബൈൽ നമ്പർ",
    inputNumber12: "മേൽവിലാസം",
    inputNumber13: "അപേക്ഷകയുടെ പേര്",
    inputNumber14: "മകൾ / മകൻ പേര്",
    inputNumber15: "ആധാർ നമ്പർ",
    inputNumber16: "ഗ്രൂപ്പിൻ്റെ പേര്",
    inputNumber17: "ഗ്രൂപ്പ് നമ്പർ",
    inputNumber18: "കസ്റ്റമർ നമ്പർ",
    inputNumber19: "അപേക്ഷിക്കുന്ന വായ്‌പ തുക",
    inputNumber20: "പ്രതിവാര തിരിച്ചടവ് തുക",
    inputNumber21: "ഭർത്താവിൻ്റെ പേര്:",
    inputNumber22: "റേഷൻ കാർഡ് നമ്പർ",
    inputNumber23: "വായ്‌പ ആവശ്യം",
    inputNumber24: "ലോൺ വ്യവസ്ഥ",
    inputNumber25: "വായ്‌പ എടുത്ത തിയതി",
    inputNumber26: "തിരിച്ചടവ് തിയതി",
    inputNumber27: "വായ്‌പ കാലാവധി",
    inputNumber28: "ആകെ തിരിച്ചടവ് തുക",
    inputNumber29: "ഉദ്ദേശ്യം",
    inputNumber30: "ഗ്രൂപ്പ് നമ്പർ",
    inputNumber31: "മെമ്പർഷിപ് നമ്പർ",
    inputNumber32: "കസ്റ്റമർ നമ്പർ",
  };

  const queryParams = new URLSearchParams(formData).toString();

  const InputSection = ({ title, startIndex, count }) => (
    <div className="form-part">
      <h3 className="part-title">{title}</h3>
      {Array.from({ length: count }, (_, index) => {
        const id = `inputNumber${startIndex + index}`;
        return (
          <div className="input-group" key={id}>
            <label>{labels[id]}</label>
            <input
              maxLength={16}
              name={id}
              value={formData[id]}
              onChange={handleChange}
              className="form-input"
            />
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="form-wrapper">
      <div className="form-container">
        <h2 className="form-title">Customer Profile Form</h2>
        
        <div className="parts-grid">
          <InputSection title="Part 1: Primary Applicant" startIndex={1} count={6} />
          <InputSection title="Part 2: Spouse Details" startIndex={7} count={6} />
          <InputSection title="Part 3: Branch Information" startIndex={13} count={8} />
          <InputSection title="Part 4: Loan Details" startIndex={21} count={8} />
          
          <div className="form-part">
            <h3 className="part-title">Part 5: Purposes</h3>
            <div className="input-group">
              <label>{labels.inputNumber29}</label>
              <input
                maxLength={16}
                name="inputNumber29"
                value={formData.inputNumber29}
                onChange={handleChange}
                className="form-input"
              />
            </div>
            <div className="input-group">
              <label>{labels.inputNumber30}</label>
              <input
                maxLength={16}
                name="inputNumber30"
                value={formData.inputNumber30}
                onChange={handleChange}
                className="form-input"
              />
            </div>
          </div>

          <div className="form-part">
            <h3 className="part-title">Part 6: Membership</h3>
            <div className="input-group">
              <label>{labels.inputNumber31}</label>
              <input
                maxLength={16}
                name="inputNumber31"
                value={formData.inputNumber31}
                onChange={handleChange}
                className="form-input"
              />
            </div>
            <div className="input-group">
              <label>{labels.inputNumber32}</label>
              <input
                maxLength={16}
                name="inputNumber32"
                value={formData.inputNumber32}
                onChange={handleChange}
                className="form-input"
              />
            </div>
          </div>
        </div>

        <div className="submit-section no-print">
          <Link
            to={{
              pathname: "/form1print",
              search: queryParams,
            }}
          >
            <button className="btn-form-print">
              <FiPrinter size={20} /> Generate Print Preview
            </button>
          </Link>
        </div>
      </div>
    </div>
  );
};

export default Form1;
