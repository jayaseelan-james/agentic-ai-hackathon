import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import Simulator from './Simulator';
import './styles.css';
const path = location.pathname.replace(/\/+$/, '') || '/';
const isBmwPath = path === '/bmw' || path === '/bmw-330i' || path === '/bmw-330i-g20';
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{path === '/simulator' ? <Simulator /> : <App initialMode={isBmwPath ? 'bmw_g20' : 'general'} />}</React.StrictMode>,
);
