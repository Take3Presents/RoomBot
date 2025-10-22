import "bootstrap/dist/css/bootstrap.css";
import "../styles/modals.css";
import Container from 'react-bootstrap/Container';
import { Col, Row } from "react-bootstrap";
import axios from 'axios';
import Button from 'react-bootstrap/Button';
import React from "react";
import Modal from 'react-bootstrap/Modal';
import Form from 'react-bootstrap/Form';
import toast from 'react-hot-toast';
import { useState } from 'react';

const someError = (msg) => toast.error("Oh No: " + msg);
const itsOK = (msg) => toast.success(msg);

export class WaittimeDelete extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      short_name: this.props.short_name,
      has_password: false,
      password: '',
      show: this.props.show,
      name: ''
    }
    this.wait_url = window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/wait/" + this.state.short_name + "/";
    this.plzDelete = this.plzDelete.bind(this);
    this.startDelete = this.startDelete.bind(this);
    this.setPassword = this.setPassword.bind(this);
    this.handleClose = this.handleClose.bind(this);
  }
  setPassword(event) {
    this.setState({password: event.target.value});
  }
  startDelete(event) {
    this.setState({show: true});
    axios.get(this.wait_url)
      .then(res => {
	if (res.data.has_password) {
	  this.setState({has_password: true});
	}
	this.setState({name: res.data.name});
      })
      .catch((error) => {
	if (error.request) {
	  someError("Network error :(");
	} else {
	  someError("Mysterious error is mysterious.");
	}
      });

  }
  plzDelete(event) {
    var data = {};
    if (this.state.has_password) {
      data.password = this.state.password;
    }
    axios.delete(this.wait_url, {data: data})
      .then(res => {
	itsOK("Deleted wait time");
	this.setState({show: false});
	this.props.reload();
      })
      .catch((error) => {
	if (error.response) {
	  if (error.response.status == 401) {
	    someError("This wait time has a password. Do you know it?")
	  } else {
	    someError("Mysterious error is mysterious.");
	  }
	} else if (error.request) {
	  someError("Network error :(");
	} else {
	  someError("Mysterious error is mysterious.");
	}
      });

  }
  handleClose() {
    this.setState({show: false});
  }
  render() {
    let maybePassword;
    if ( this.state.has_password ) {
      maybePassword = (
	<>
	  <span>This wait time has a password that must be provided.</span>
	  <Form.Group className="mb-3" controlId="exampleForm.ControlTextarea4">
            <Form.Label>Password</Form.Label>
            <Form.Control type="password" name="inputName" onChange={this.setPassword}/>
	  </Form.Group>
	</>
      )
    }

    return (
      <>
	<Button variant={"outline-primary"} size="sm" onClick={this.startDelete}>
	  Delete
	</Button>
	<Modal show={this.state.show} onHide={this.handleClose}>
	  <Modal.Header closeButton>
	    <Modal.Title>Delete {this.state.name}???</Modal.Title>
	  </Modal.Header>
	  <Modal.Body>
	    {maybePassword}
	    <Button variant={"danger"} size="sm" onClick={this.plzDelete}>
	      Really Delete?????
	    </Button>
	  </Modal.Body>
	</Modal>
      </>
    )
  }
}

export class WaittimeEdit extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      short_name: this.props.short_name ? this.props.short_name : '',
      name: '',
      time: '',
      new_password: '',
      show: this.props.show,
      is_new: true,
      has_password: false,
      password: true,
      hours: 0,
      minutes: 0,
      seconds: 0,
      countdown: false,
      free_update: false
    };
    this.wait_url = window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/wait/";
    this.startEdit = this.startEdit.bind(this);
    this.handleClose = this.handleClose.bind(this);
    this.setNewPassword = this.setNewPassword.bind(this);
    this.setName = this.setName.bind(this);
    this.setShortName = this.setShortName.bind(this);
    this.handleSubmit = this.handleSubmit.bind(this);
    this.setPassword = this.setPassword.bind(this);
    this.setHours = this.setHours.bind(this);
    this.setMinutes = this.setMinutes.bind(this);
    this.setSeconds = this.setSeconds.bind(this);
    this.setCountdown = this.setCountdown.bind(this);
    this.setFreeUpdate = this.setFreeUpdate.bind(this);
  }

  startEdit(event) {
    if (this.state.short_name) {
      this.state.is_new = false;
    }
    this.setState({
      show: true,
      new_password: ''
    });
    if (! this.state.is_new) {
      axios.get(this.wait_url + this.state.short_name + "/")
	.then(res => {
	  var hours = Math.floor(res.data.time / 3600);
	  var minutes = Math.floor((res.data.time - (hours * 3600)) / 60);
	  var seconds = res.data.time - (hours * 3600) - (minutes * 60);
	  this.setState({
	    name: res.data.name,
	    time: res.data.time,
	    hours: hours,
	    minutes: minutes,
	    seconds: seconds,
	    countdown: res.data.countdown,
	    free_update: res.data.free_update
	  });
	  if (res.data.has_password) {
	    this.setState({has_password: true});
	  }
	})
        .catch((error) => {
	  if (error.request) {
	    someError("Network error :(");
	  } else {
	    someError("Mysterious error is mysterious.");
	  }
	});
    }
  }

  setName(event) {
    this.setState({name: event.target.value});
  }

  setShortName(event) {
    var short_name = event.target.value
	.replaceAll(/[^a-zA-Z0-9-_]/g, '');
    this.setState({short_name: short_name});
  }

  setCountdown(event) {
    this.setState({countdown: event.target.checked});
  }

  setFreeUpdate(event) {
    this.setState({free_update: event.target.checked});
  }

  setNewPassword(event) {
    this.setState({new_password: event.target.value});
  }

  setPassword(event) {
    this.setState({password: event.target.value});
  }

  setHours(event) {
    var hours = parseInt(event.target.value);
    if ( isNaN(hours)) {
      hours = 0;
    }
    this.setState({
      hours: hours
    });
  }

  setMinutes(event) {
    var minutes = parseInt(event.target.value);
    if (isNaN(minutes)) {
      minutes = 0;
    } else if ( minutes > 59 ) {
      minutes = 59;
    }
    this.setState({
      minutes: minutes
    });
  }

  setSeconds(event) {
    var seconds = parseInt(event.target.value);
    if ( isNaN(seconds)) {
      seconds = 0;
    } else if ( seconds > 59 ) {
      seconds = 59;
    }
    this.setState({
      seconds: seconds,
    });
  }

  handleClose() {
    this.setState({show: false});
  }
  handleSubmit(event) {
    event.preventDefault();
    var data = {
	time: this.state.seconds + (this.state.minutes * 60) + (this.state.hours * 3600),
	countdown: this.state.countdown,
	free_update: this.state.free_update,
	name: this.state.name
    }
    if (! this.state.is_new) {
      if ( this.state.has_password ) {
	data.password = this.state.password;
      }
      if ( this.state.new_password != '' ) {
	data.new_password = this.state.new_password;
      }
    } else {
      data.short_name = this.state.short_name;
      if (this.state.new_password != '') {
	data.password = this.state.new_password;
      }
    }
    if ( ! this.state.is_new ) {
      axios.put(this.wait_url + this.state.short_name + "/", data)
	.then(res => {
	  this.props.reload();
	  this.setState({show: false});
	})
      	.catch((error) => {
	  if (error.response) {
	    if (error.response.status == 400) {
	      someError("Unable to edit waittime!");
	    } else if (error.response.status == 401) {
	      if (error.response.data != '') {
		someError(error.response.data);
	      } else {
		someError("This wait time has a password. Do you know it?");
	      }
	    } else {
	      someError("Mysterious error is mysterious.");
	    }
	  } else if (error.request) {
	    someError("Network error :(");
	  } else {
	    someError("Mysterious error is mysterious.");
	  }
	});
    } else {
      axios.post(this.wait_url, data)
	.then(res => {
	  this.props.reload();
	  this.setState({show: false});
	})
	.catch((error) => {
	  if (error.response && error.response.status == 400) {
	    someError("Unable to create waittime!");
	  } else if (error.request) {
	    someError("Network error :(");
	  } else {
	    someError("Mysterious error is mysterious.");
	  }
	});
    }
  }
  render(){
    let maybeShortName;
    let maybePassword;
    let maybeDisabled;
    if ( this.state.is_new ) {
      maybeShortName = (
	<Form.Group className="mb-3" controlId="exampleForm.ControlTextarea3">
          <Form.Label>The wait time <i>short name</i> is used as part of the URL and must be unique</Form.Label>
          <Form.Control type="text" name="inputShortName" value={this.state.short_name} onChange={this.setShortName}/>
	</Form.Group>
      );
    }
    if ( this.state.has_password ) {
      maybePassword = (
	<>
	<span>This waittime has a password. You <i>must</i> include it to make edits.</span>
	<Form.Group className="mb-3" controlId="exampleForm.ControlTextarea4">
          <Form.Label>Waittime Password</Form.Label>
          <Form.Control type="password" name="inputName" onChange={this.setPassword}/>
	</Form.Group>
	</>
      )
    }
    return (
      <>
      <Button variant={"outline-primary"} size="sm" onClick={this.startEdit}>
      { this.state.short_name ? "Edit Waittime" : "New Waittime" }
      </Button>
      <Modal show={this.state.show} onHide={this.handleClose}>
        <Modal.Header closeButton>
          <Modal.Title>{ this.state.short_name ? "Edit Waittime: " + this.state.name : "New Waittime" }</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form onSubmit={this.handleSubmit}>
	    {maybeShortName}
	    {maybePassword}
	    <Form.Group className="mb-3" controlId="exampleForm.name">
              <Form.Label>A <i>descriptive</i> name for the wait time</Form.Label>
              <Form.Control type="text" name="inputName" value={this.state.name} onChange={this.setName} />
	    </Form.Group>
	    <Container fluid>
	      <Row>
		<Col className="col-6">
		  <Form.Group className="mb-3" controlId="exampleForm.countdown">
		    <Form.Label>If this box is checked the wait time will count down for the specified period, starting from when it was last updated</Form.Label>
		    <Form.Check type="checkbox" name="inputCountdown" checked={this.state.countdown} onChange={this.setCountdown} />
		  </Form.Group>
		</Col>
		<Col className="col-2">
		  <Form.Group className="mb-3" controlId="exampleForm.hours">
		    <Form.Label>Hours</Form.Label>
		    <Form.Control type="text" name="inputHours" value={this.state.hours} onChange={this.setHours} onFocus={(event) => event.target.select()}/>
		  </Form.Group>
		</Col>
		<Col className="col-2">
		  <Form.Group className="mb-3" controlId="exampleForm.minutes">
		    <Form.Label>Minutes</Form.Label>
		    <Form.Control type="text" name="inputMinutes" value={this.state.minutes} onChange={this.setMinutes} onFocus={(event) => event.target.select()}/>
		  </Form.Group>
		</Col>
		<Col className="col-2">
		  <Form.Group className="mb-3" controlId="exampleForm.seconds">
		    <Form.Label>Seconds</Form.Label>
		    <Form.Control type="text" name="inputSeconds" value={this.state.seconds} onChange={this.setSeconds} onFocus={(event) => event.target.select()}/>
		  </Form.Group>
		</Col>
	      </Row>
	    </Container>
	    <Container fluid>
	      <Row>
		<Col className="col-3">
		  <Form.Group className="mb-3" controlId="exampleForm.countdown">
		    <Form.Label>Anyone can always update the wait time</Form.Label>
		    <Form.Check type="checkbox" name="inputFreeUpdate" checked={this.state.free_update} onChange={this.setFreeUpdate} />
		  </Form.Group>
		</Col>
		<Col className="col-9">
		  <Form.Group className="mb-3" controlId="exampleForm.new_password">
		    <Form.Label>You may (optionally) specifiy a password so that only certain folk can update this wait time </Form.Label>
		    <Form.Control type="password" name="password" onChange={this.setNewPassword} />
		  </Form.Group>
		</Col>
	      </Row>
	    </Container>
            <Button variant="primary" type="submit">
              Submit
            </Button>
          </Form>
        </Modal.Body>
      </Modal>
      </>
    )
  }
}
