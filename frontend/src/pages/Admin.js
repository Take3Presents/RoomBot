
import RoombotAdmin from '../components/admin.js';
import BasicVis from '../components/adminMetrics.js';
import "../styles/RoombotAdmin.css";
import React, { useState } from 'react';
import { Toaster } from 'react-hot-toast';

const AppAdmin = () => {
  const [count, setCount] = useState(0);
  const [systemNotice, setSystemNotice] = useState(null);

  const onChange = () => {
    setCount(count + 1);
  }

  // Check for system notice from JWT login response
  React.useEffect(() => {
    const jwt = JSON.parse(localStorage.getItem('jwt'));
    if (jwt && jwt.system_notice) {
      setSystemNotice(jwt.system_notice);
    }
  }, []);
	
  return(
    <div className="componentContainer">

      <div className="AppHeader">
	<img src="roombaht_header.png" alt="RoomBaht9000" />
      </div>

      {systemNotice && (
        <div className="alert alert-warning" role="alert">
          <strong>System Notice:</strong> {systemNotice}
        </div>
      )}

      <div className="DTApp"> Roombot Metrics
        <BasicVis count={count} />
      </div>

      <div className="DTApp"> Roombot Admin
        <RoombotAdmin onChange={onChange}/>
      </div>
      <Toaster />
    </div>
  );
};

export default AppAdmin;
