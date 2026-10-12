import { configureStore } from "@reduxjs/toolkit";
import myfinSlice from "./MyfinSlice";
import { persistStore, persistReducer } from 'redux-persist'
import storage from 'redux-persist/lib/storage';
const persistConfig = {
  key: 'root',
  storage:storage,
}
const persistedReducer = persistReducer(persistConfig,myfinSlice.reducer )
const store = configureStore({
  middleware: getDefaultMiddleware =>
    getDefaultMiddleware({
      serializableCheck: false,
    }),
  reducer: {
    myfin: persistedReducer,
    
  },
});
export const persistor = persistStore(store)
export default store;
