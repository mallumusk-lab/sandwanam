import React, { useEffect } from "react";
import { useDispatch } from "react-redux";
import { Myaction } from "../../store/MyfinSlice";
import Analytics from "../Analytics/Analytics";

const AdminPage = () => {
  const dispatch = useDispatch();

  useEffect(() => {
    const storedUser = localStorage.getItem("selectedUser");
    if (storedUser) {
      dispatch(Myaction.userChangeSelected(storedUser));
    } else {
      dispatch(Myaction.userChangeSelected("User1"));
      localStorage.setItem("selectedUser", "User1");
    }
  }, [dispatch]);

  return <Analytics />;
};

export default AdminPage;
