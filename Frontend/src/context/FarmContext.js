import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const API_URL = `${(process.env.REACT_APP_API_URL || "https://laviprina-project.vercel.app").replace(/\/+$/, "")}/api`;
const FarmContext = createContext(null);

export function FarmProvider({ children }) {
  const [token, setTokenState] = useState(() => localStorage.getItem("kr-token"));
  const [animals, setAnimals] = useState([]);
  const [dairyCows, setDairyCows] = useState([]);
  const [milkRecords, setMilkRecords] = useState([]);
  const [healthRecords, setHealthRecords] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [reports, setReports] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const setToken = useCallback((value) => {
    if (value) {
      localStorage.setItem("kr-token", value);
    } else {
      localStorage.removeItem("kr-token");
    }
    setTokenState(value);
  }, []);

  const request = useCallback(async (path, options = {}) => {
    let response;
    try {
      response = await fetch(`${API_URL}${path}`, {
        method: options.method || "GET",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      });
    } catch {
      throw new Error("Cannot reach the server. Check that the backend is running.");
    }

    let data = {};
    const responseText = await response.text();
    if (responseText) {
      try {
        data = JSON.parse(responseText);
      } catch {
        throw new Error("The server returned an invalid JSON response.");
      }
    }

    if (!response.ok) {
      if (response.status === 401) {
        setToken(null);
      }
      throw new Error(data.error || data.msg || `Request failed (HTTP ${response.status})`);
    }
    return data;
  }, [setToken, token]);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const [animalRows, dairyRows, milkRows, healthRows, inventoryRows, transactionRows, summary] =
        await Promise.all([
          request("/animals"),
          request("/dairy-cows"),
          request("/milk"),
          request("/health-records"),
          request("/inventory"),
          request("/transactions"),
          request("/reports/summary"),
        ]);
      setAnimals(animalRows);
      setDairyCows(dairyRows);
      setMilkRecords(milkRows);
      setHealthRecords(healthRows);
      setInventory(inventoryRows);
      setTransactions(transactionRows);
      setReports(summary);
    } catch (loadError) {
      setError(loadError.message);
      throw loadError;
    } finally {
      setLoading(false);
    }
  }, [request, token]);

  useEffect(() => {
    if (token) {
      refresh().catch(() => {});
    } else {
      setAnimals([]);
      setDairyCows([]);
      setMilkRecords([]);
      setHealthRecords([]);
      setInventory([]);
      setTransactions([]);
      setReports(null);
      setError("");
    }
  }, [refresh, token]);

  const value = useMemo(() => ({
    token,
    setToken,
    request,
    refresh,
    animals,
    dairyCows,
    milkRecords,
    healthRecords,
    inventory,
    transactions,
    reports,
    loading,
    error,
    setError,
  }), [
    token, setToken, request, refresh, animals, dairyCows, milkRecords,
    healthRecords, inventory, transactions, reports, loading, error,
  ]);

  return <FarmContext.Provider value={value}>{children}</FarmContext.Provider>;
}

export function useFarm() {
  const context = useContext(FarmContext);
  if (!context) {
    throw new Error("useFarm must be used within a FarmProvider");
  }
  return context;
}
