import "../styles/WaitTimes.css";
import { TheTimers, HowLongTho } from "../components/waittimes.js";
import React, { useEffect, useState } from "react";
import { Toaster } from 'react-hot-toast';

export function Waittime() {
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
        if (!data.features.includes('waittime')) {
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
    <div className="componentContainer">
      <div className="AppHeader">
	    <img src="/roombaht_header.png" alt="RoomBaht9000" />
      </div>

      <div className="DTApp">
        <HowLongTho redirectUrl={redirectUrl} />
      </div>

      <div className="AppNav">
	      <a href="/waittime">Wait Times</a>
      </div>
    </div>
  );
};

export function WaittimeList() {
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
        if (!data.features.includes('waittime')) {
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

      <div className="AppHeader">
          <img src="/roombaht_header.png" alt="RoomBaht9000" />
      </div>

      <div className="DTApp">Wait Times for the people because the people need to Wait
        <TheTimers redirectUrl={redirectUrl} />
      </div>

    </div>
    <Toaster/>
    </>
  );
};
