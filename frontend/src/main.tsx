import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import Simulator from './Simulator';
import './styles.css';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{location.pathname === '/simulator' ? <Simulator /> : <App />}</React.StrictMode>);
