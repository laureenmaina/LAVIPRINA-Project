import React from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import FarmNav from './components/FarmNav';
import { Notice } from './components/FarmCommon';
import { FarmProvider, useFarm } from './context/FarmContext';
import Aboutus from './pages/Aboutus';
import Breeding from './pages/breeding';
import Contactus from './pages/contactus';
import Dashboard from './pages/Dashboard';
import Feeds from './pages/feeds';
import Inventory from './pages/inventory';
import Login from './pages/Login';
import MilkRecords from './pages/milkrecords';
import Sales from './pages/sales';
import './FarmApp.css';

function ProtectedLayout() {
    const { token, error, refresh } = useFarm();
    if (!token) return <Navigate to="/login" replace />;
    return (
        <>
            <FarmNav />
            <main className="app-main">
                {error && <div className="global-error"><Notice error>{error}</Notice><button className="button secondary small" onClick={() => refresh().catch(() => {})}>Retry</button></div>}
                <Outlet />
            </main>
        </>
    );
}

const App = () => (
    <FarmProvider>
        <BrowserRouter>
            <Routes>
                <Route path="/login" element={<Login />} />
                <Route element={<ProtectedLayout />}>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/milkrecords" element={<MilkRecords />} />
                    <Route path="/inventory" element={<Inventory />} />
                    <Route path="/feeds" element={<Feeds />} />
                    <Route path="/breeding" element={<Breeding />} />
                    <Route path="/sales" element={<Sales />} />
                    <Route path="/aboutus" element={<Aboutus />} />
                    <Route path="/contactus" element={<Contactus />} />
                    <Route path="/animals/:animalId" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/register" element={<Navigate to="/dashboard" replace />} />
                </Route>
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
        </BrowserRouter>
    </FarmProvider>
);

export default App;
