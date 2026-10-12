import { createSlice } from "@reduxjs/toolkit";
// const storedData = JSON.parse(localStorage.getItem("myfinData"));
const myfinSlice = createSlice({
  name: "myfin",
  initialState: {
    data: "",
    statement: {},
    loanDetailsOfCustomer: [],
    user: "User1",
    loanFullData:[],
    refresh:true,
    reportLoanNumber: null,
  },
  reducers: {
    dataReducer(state, action) {
      state.data = action.payload.data.role;
console.log('====================================');
console.log("redux", state.data);
console.log('====================================');
      localStorage.setItem("myfinData", JSON.stringify(state.data));
    },
    clearData(state) {
      state.data = {};
      localStorage.removeItem("myfinData");
    },
    loanFullDataSelected(state,actions){
      state.loanFullData=actions.payload
    },
    refreshSelected(state,action){
      state.refresh=action.payload
    },
    userChangeSelected(state, actions) {
      // console.log('====================================');
      // console.log("actions  "+actions.payload);
      // console.log('====================================');
      state.user = actions.payload;
    },
    userNotChangeSelected(state, action) {
      state.user = action.payload;
    },
    reportLoanNumber(state, action) {
      state.reportLoanNumber = action.payload;
    },
    // setUserData(state, action) {
    //   state.userData = action.payload;
    // },
  },
});

export const Myaction = myfinSlice.actions;
export default myfinSlice;
