
import React, { useState, useEffect } from 'react';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Modal from 'react-bootstrap/Modal';
import axios from 'axios';
import toast, { Toaster } from 'react-hot-toast';
import "../styles/modals.css";
const swapError = (msg) => toast.error("Swap error: " + msg);
const someError = (msg) => toast.error("Oh No: " + msg);

export function ModalParty(props) {
  const [show, setShow] = useState(false);
  const [description, setDescription] = useState('');
  const handleClose = () => setShow(false);
  const handleShow = () => {
    axios.get(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/party/" + props.room_number + "/")
      .then(res => {
	setDescription(res.data.description);
	setShow(true);
      })
      .catch((error) => {
	someError("Unable to retrieve party info :(")
      });
  }

  return (
    <>
      <Button variant={"info"} size="sm" onClick={handleShow}>I Am A Party</Button>
      <Modal show={show} onHide={handleClose}>
	<Modal.Header closeButton>
	  <Modal.Title>Party in {props.room_number}</Modal.Title>
	</Modal.Header>
	<Modal.Body>
	  {description}
	</Modal.Body>
      </Modal>
    </>
  )
}

export function ModalRequestSwap(props) {
  const [show, setShow] = useState(false);
  const handleClose = () => setShow(false);
  const handleShow = () => setShow(true);
  const [phrase, setPhrase] = useState("");
  const jwt = JSON.parse(localStorage.getItem('jwt'));
  const row = props.row;
  const handleAPICall = (contacts) => {
    if (contacts === null) {
        return;
    }
    axios.post(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/swap_request/", {
      jwt: jwt["jwt"],
      number: row.number,
      hotel: row.name_hotel,
      contact_info: contacts
    })
      .then(res => {
	toast.success("Swap request sent.");
      })
      .catch((error) => {
        if (error.response) {
	  if ( error.response.status == 400 ) {
	    var msg = "Unacceptable swap requested";
	    if (error.response.data) {
	      msg = msg + ": " + error.response.data;
	    }
	    swapError(msg);
	  } else {
            console.log("server responded");
            console.log(error.response.data);
	    swapError("Server responded with error. contact placement@take3presents.com");
	  }
        } else if (error.request) {
	  swapError("Network error. Please try again later.");
        } else {
	  swapError("Mysterious error is mysterious.");
          console.log(error);
        }
      });
  }

  const handleSubmit = (evt) => {
    evt.preventDefault();
    const formData = new FormData(evt.target),
      formDataObj = Object.fromEntries(formData.entries())
      handleAPICall(formDataObj.inputSwapCode);

  };

  return (
    <>
      {props.swaps_enabled ?
      <Button disabled={row.available && row.is_swappable ? false : true}
	    variant={row.available && row.is_swappable ? "outline-primary" : "outline-secondary"}
            size="sm"
            onClick={handleShow}>
            SendSwapRequest
      </Button>
       :
       <Button hidden disabled={row.available ? false : true}
	    variant={row.available ? "outline-primary" : "outline-secondary"}
            size="sm"
            onClick={handleShow}>
            SendSwapRequest
      </Button>
      }
      <Modal show={show} onHide={handleClose}>
        <Modal.Header closeButton>
          <Modal.Title>RoomService Room Trader</Modal.Title>
        </Modal.Header>
        <Modal.Body>

          <h5>System Live</h5>
          <p>Ok fam so rly we can only do so much for you here.</p>
          <p>We can send the owner of this room an email with your contact info, but we can’t make them look at their phone or want to swap rooms with you. So. If you have another way of reaching this person, go for it.</p>
          <p>Once you are in contact and both agree to the swap, click the CreateSwapCode button on your room. Send the code to the other person and have them enter it.</p>
          <p>Enter your email address and/or phone number so the owner of the room you want can contact you.</p>

          <Form onSubmit={handleSubmit}>

            <Form.Group className="mb-3" controlId="exampleForm.ControlTextarea1">
              <Form.Label>Your Contact Info:</Form.Label>
              <Form.Control type="text" name="inputSwapCode" />
            </Form.Group>

          <Button variant="primary" type="submit">
            Submit
          </Button>
          </Form>

        </Modal.Body>
        <Modal.Footer>
          {phrase}
        </Modal.Footer>
      </Modal>
    </>
  );
}


export function ModalEnterCode(props) {
  const [show, setShow] = useState(false);
  const handleClose = () => setShow(false);
  const handleShow = () => setShow(true);
  const [phrase, setPhrase] = useState("");
  const jwt = JSON.parse(localStorage.getItem('jwt'));
  const row = props.row.number;

  const handleAPICall = (code) => {
    axios.post(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/swap_it_up/", {
        jwt: jwt['jwt'],
        number: row,
        swap_code: code
      })
      .then(res => {
        setPhrase(res.data);
        handleClose();
      })
      .catch((error) => {
        if (error.response) {
	  if ( error.response.status == 400 ) {
	    var msg = "Unacceptable swap requested";
	    if (error.response.data) {
	      msg = msg + ": " + error.response.data;
	    }
	    swapError(msg);
	  } else {
            console.log("server responded");
            console.log(error.response.data);
	    swapError("Server responded with error. contact placement@take3presents.com");
	  }
        } else if (error.request) {
	  swapError("Network error. Please try again later.");
        } else {
	  swapError("Mysterious error is mysterious.");
          console.log(error);
        }
      });
  }

  const handleSubmit = (evt) => {
    evt.preventDefault();
    const formData = new FormData(evt.target),
      formDataObj = Object.fromEntries(formData.entries())
      handleAPICall(formDataObj.inputSwapCode);

  };

  return (
    <>
      {props.swaps_enabled ?
       <Button disabled={props.row.swappable ? false : true} size="sm" variant={props.row.cooldown ? "outline-info" : props.row.swappable ? "outline-primary" : "outline-secondary"} onClick={handleShow}>
          EnterSwapCode
      </Button>
       :
      <Button hidden size="sm" variant="outline-primary" onClick={handleShow}>
          EnterSwapCode
      </Button>
      }

      <Modal show={show} onHide={handleClose} onExited={props.onExited}>
        <Modal.Header closeButton>
          <Modal.Title>RoomService Room Trader</Modal.Title>
        </Modal.Header>
        <Modal.Body>

          <h5>System Live</h5>
          <p>Be sure you want to trade this room with the one associated with the code you are about to enter. No take-backzies.</p>
          <Form onSubmit={handleSubmit}>

            <Form.Group className="mb-3" controlId="exampleForm.ControlTextarea1">
              <Form.Label>Input the SwapCode sent to you</Form.Label>
              <Form.Control type="text" name="inputSwapCode" />
            </Form.Group>

          <Button variant="primary" type="submit">
            Submit
          </Button>
          </Form>

        </Modal.Body>
        <Modal.Footer>
          {phrase}
        </Modal.Footer>
      </Modal>
    </>
  );
}

export function ModalCreateCode(props) {
  var refreshTimer = null;
  const [show, setShow] = useState(false);
  const [phrase, setPhrase] = useState("");

  const jwt = JSON.parse(localStorage.getItem('jwt'));
  const row = props.row.number;
  const handleClose = () => {
    if ( refreshTimer !== null ) {
      clearInterval(refreshTimer);
    }
    setShow(false);
  }
  const handleShow = () => {
    refreshTimer = setInterval(() =>
      {
	axios.post(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/my_rooms/", {
	  jwt: jwt["jwt"]
	})
	  .then(res => {
	    var hasSwapped = true;
	    res.data.rooms.forEach((room) => {
	      if (room.number == row) {
		hasSwapped = false;
	      }
	    });
	    if (hasSwapped) {
	      handleClose();
	    }
	  })

      }, 5000);
    setShow(true);
  }
  const handleAPICall = () => {

    axios.post(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/swap_gen/", {
            jwt: jwt['jwt'],
            number: {row},
      })
      .then(res => {
        const phrase = res.data.swap_phrase;
        setPhrase(phrase);
        handleShow();
      })
      .catch((error) => {
        if (error.response) {
	  if ( error.response.status == 400 ) {
	    var msg = "Unacceptable swap requested";
	    if (error.response.data) {
	      msg = msg + ": " + error.response.data;
	    }
	    swapError(msg);
	  } else {
            console.log("server responded");
            console.log(error.response.data);
	    swapError("Server responded with error. contact placement@take3presents.com");
	  }
        } else if (error.request) {
	  swapError("Network error. Please try again later.");
        } else {
	  swapError("Mysterious error is mysterious.");
          console.log(error);
        }
      });
  }


  return (
    <>
      {props.swaps_enabled ?
       <Button disabled={props.row.swappable ? false : true} size="sm" variant={props.row.cooldown ? "outline-info" : props.row.swappable ? "outline-primary" : "outline-secondary"} onClick={handleAPICall}>
          CreateSwapCode
      </Button>
       :
      <Button hidden size="sm" variant="outline-primary" onClick={handleAPICall}>
          CreateSwapCode
      </Button>
      }

      <Modal show={show} onHide={handleClose} onExited={props.onExited}>

        <Modal.Header closeButton>
          <Modal.Title>RoomService Swapcode Generator</Modal.Title>
        </Modal.Header>

        <Modal.Body>
          <h5>Send this code to your friend if u rly want to trade roomz with them.</h5>
          <p/>
          <p>Direct them to follow the link in the request email, or initial placement email. Have them click EnterSwapCode on the room they are trading to you.</p>
          <p>This code expires after 10mins. No un-swapzies.</p>
          <p>Swap Code: {phrase}</p>
        </Modal.Body>

        <Modal.Footer>
          <Button variant="primary" onClick={handleClose}>
            Close
          </Button>
        </Modal.Footer>

      </Modal>
    </>
  );
}


