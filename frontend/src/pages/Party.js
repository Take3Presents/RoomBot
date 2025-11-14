import "../styles/party.css";
import { TheParties } from "../components/party.js";
import React, { useEffect, useState } from "react";
import { Toaster } from 'react-hot-toast';

export function PartyFinder() {
  const [redirectUrl, setRedirectUrl] = useState(null);

  useEffect(() => {
    const baseUrl = window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000");
    fetch(baseUrl + '/api/login/')
      .then(response => {
        if (response.status === 501) {
          window.location.href = 'https://zombo.com';
          return;
        }
        return response.json();
      })
      .then(data => {
        if (!data) return;
        if (!data.features.includes('party')) {
          window.location.href = data.disabled_redirect_url;
        } else {
          setRedirectUrl(data.disabled_redirect_url);
        }
      })
      .catch(error => {
        console.error('Error checking features:', error);
      });
  }, []);

  return(
    <>
    <div className="componentContainer">
      <div className="DTApp partyApp">
	<span className="display-3">Where da party at tho</span>
        <TheParties redirectUrl={redirectUrl} />
      </div>
    </div>
    <Toaster/>
    </>
  );
};
