import "bootstrap/dist/css/bootstrap.css";
import "../styles/modals.css";
import Container from 'react-bootstrap/Container';
import { Col, Row, Table } from "react-bootstrap";
import {
  DatatableWrapper,
  TableBody,
  TableColumnType,
  TableHeader
} from "react-bs-datatable";
import { WaittimeEdit, WaittimeDelete } from "./waittimes_edit.js";
import axios from 'axios';
import Button from 'react-bootstrap/Button';
import React from "react";
import Modal from 'react-bootstrap/Modal';
import Form from 'react-bootstrap/Form';
import toast, { Toaster } from 'react-hot-toast';
import { useParams } from "react-router-dom";
import { Display } from "react-7-segment-display";
const someError = (msg) => toast.error("Oh No: " + msg);

function withParams(Component) {
  return props => <Component {...props} params={useParams()} />;
}

class UpdateTime extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      short_name: props.short_name,
      time: props.time,
      show: props.show,
      hours: 0,
      minutes: 0,
      seconds: 0
    }
    this.state.hours = Math.floor(this.state.time / 3600);
    this.state.minutes = Math.floor((this.state.time - (this.state.hours * 3600)) / 60);
    this.state.seconds = this.state.time - (this.state.hours * 3600) - (this.state.minutes * 60);

    this.setHours = this.setHours.bind(this);
    this.setMinutes = this.setMinutes.bind(this);
    this.setSeconds = this.setSeconds.bind(this);
    this.handleClose = this.handleClose.bind(this);
    this.startEdit = this.startEdit.bind(this);
    this.handleSubmit = this.handleSubmit.bind(this);
  }

  handleClose() {
    this.setState({show: false});
  }

  startEdit(event) {
    this.setState({show: true});
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
  handleSubmit(event) {
    event.preventDefault();
    var data = {
      time: this.state.seconds + (this.state.minutes * 60) + (this.state.hours * 3600)
    }
    axios.put(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/wait/" + this.state.short_name + "/", data)
      .then(res => {
	this.setState({show: false});
	this.props.reload();
      })
      .catch((error) => {
	if (error.response) {
	  if (error.response.status == 501 && this.props.redirectUrl) {
	    window.location.href = this.props.redirectUrl;
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
  render() {
    return (
      <>
	<Button variant={"secondary"} size="sm" onClick={this.startEdit} key={Math.random()}>
	  Update this wait time
	</Button>
	<Modal show={this.state.show} onHide={this.handleClose}>
	  <Modal.Header closeButton>
	    <Modal.Title>Update Time</Modal.Title>
	  </Modal.Header>
	  <Modal.Body>
            <Form onSubmit={this.handleSubmit}>
	      <Container fluid>
		<Row>
		  <Col className="col-2">
		    <Form.Group className="mb-3" controlId="exampleForm.hours">
		      <Form.Label>Hours</Form.Label>
		      <Form.Control type="text" name="inputHours" value={this.state.hours} onChange={this.setHours} onFocus={(event) => event.target.select()}/>
		    </Form.Group>
		  </Col>
		  <Col className="col-3">
		    <Form.Group className="mb-3" controlId="exampleForm.minutes">
		      <Form.Label>Minutes</Form.Label>
		      <Form.Control type="text" name="inputMinutes" value={this.state.minutes} onChange={this.setMinutes} onFocus={(event) => event.target.select()}/>
		    </Form.Group>
		  </Col>
		  <Col className="col-4">
		    <Form.Group className="mb-3" controlId="exampleForm.seconds">
		      <Form.Label>Seconds</Form.Label>
		      <Form.Control type="text" name="inputSeconds" value={this.state.seconds} onChange={this.setSeconds} onFocus={(event) => event.target.select()}/>
		    </Form.Group>
		  </Col>
		</Row>
	      </Container>
              <Button variant="primary" type="submit">
		Update
              </Button>
	    </Form>
	  </Modal.Body>
	</Modal>
      </>
    )
  }
}

class aaaHowLongTho extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      short_name: this.props.params.slug,
      name: '',
      seconds: '',
      minutes: '',
      hours: '',
      lenght: 0,
      time: 0,
      countdown: false,
      updated: 0,
      timer: null,
      free_update: false,
      has_password: false
    }
    this.wait_url = window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/wait/" + this.state.short_name + "/";
    this.updateTime = this.updateTime.bind(this);
    this.loadWait = this.loadWait.bind(this);
  }
  updateTime() {
    var hours, minutes, seconds;
    var actual_time  = this.state.time;
    if ( this.state.countdown ) {
      var actual_time = this.state.time - (Math.floor(Date.now() / 1000) - this.state.updated);
      if (actual_time > 0) {
	setTimeout(() => this.updateTime(), 1000);
      } else {
	actual_time = 0;
      }
    }
    hours = Math.floor(actual_time / 3600);
    minutes = Math.floor((actual_time - (hours * 3600)) / 60);
    seconds = actual_time - (hours * 3600) - (minutes * 60);
    this.setState({
      hours: hours,
      minutes: minutes,
      seconds: seconds,
    });
  }
  loadWait() {
    axios.get(this.wait_url)
      .then((result) => {
	clearTimeout(this.state.timer);	
	this.setState({timer: setTimeout(() => this.loadWait(), 15000),
		       name: result.data.name,
		       time: result.data.time,
		       countdown: result.data.countdown,
		       updated: Math.floor(new Date(result.data.updated_at).getTime() / 1000),
		       free_update: result.data.free_update,
		       has_password: result.data.has_password,
		       short_name: result.data.short_name
		      }, () => this.updateTime());
      })
      .catch((error) => {
	if (error.response && error.response.status == 501 && this.props.redirectUrl) {
	  window.location.href = this.props.redirectUrl;
	}
      });
  }
  componentDidMount() {
    this.loadWait();
  }
  render() {
    let maybeUpdateTime
    if (this.state.time > 0 && (this.state.free_update || !this.state.has_password)) {
      maybeUpdateTime = (
	<Col className="buttonCol">
	  <UpdateTime short_name={this.state.short_name} time={this.state.time} reload={this.loadWait} redirectUrl={this.props.redirectUrl} />
	</Col>
      )
    }
    return(
      <>
	  <Container fluid className="border border-light rounded mb-0">
	    <Row>
	      <Col>
            <p></p>
            <h3 className="card-subtitle mb-2 text-muted">Wait time: {this.state.name}</h3>
	      </Col>
	    </Row>
	    <Row>
	    </Row>
	    <Row>
	      <Col className="d-flex justify-content-center">
	        <Display value={this.state.hours ? this.state.hours : '00'} skew="true" height="100" count="3"/>
	        <Col className="timerClass">Hr</Col>
	      </Col>
	      <Col className="d-flex justify-content-center">
	        <Display value={this.state.minutes ? this.state.minutes : '00'} skew="true" height="100"/>
	        <Col className="timerClass">Min</Col>
	      </Col>
	      <Col className="d-flex justify-content-center">
	        <Display value={this.state.seconds ? this.state.seconds : '00'} skew="true" height="100"/>
	        <Col className="timerClass">Sec</Col>
	      </Col>
	    </Row>
        <Row>
	      {maybeUpdateTime}
	    </Row>
	</Container>
      </>
    )
  }
};
export const HowLongTho = withParams(aaaHowLongTho);

export class TheTimers extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      waittimes: []
    };
    this.loadWaits = this.loadWaits.bind(this);
  }

  loadWaits() {
    axios.get(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/wait/")
      .then((result) => {
	    this.setState({waittimes: result.data});
      })
      .catch((error) => {
	if (error.response && error.response.status == 501 && this.props.redirectUrl) {
	  window.location.href = this.props.redirectUrl;
	}
      });
  }

  componentDidMount() {
    this.loadWaits()
  }

  waitHeaderFactory() {
    let WAIT_HEADERS: TableColumnType<ArrayElementType>[] = [
      {
	prop: "name",
	cell: (row) => ( <a href={"/waittime/" + row.short_name}>{row.name}</a> ),
	title: "Name"
      },
      {
	prop: "button",
	cell: (row) => ( <WaittimeEdit key={Math.random()} short_name={row.short_name} reload={this.loadWaits} redirectUrl={this.props.redirectUrl}/> )
      },
      {
	prop: "button",
	cell: (row) => ( <WaittimeDelete key={Math.random()} short_name={row.short_name} reload={this.loadWaits} redirectUrl={this.props.redirectUrl}/> )
      }

    ];
    return WAIT_HEADERS;
  }
  render(){
    return(
      <>
      <div>
	<WaittimeEdit key={Math.random()} reload={this.loadWaits} redirectUrl={this.props.redirectUrl}/>
      </div>
      <div>
	<DatatableWrapper body={this.state.waittimes} headers={this.waitHeaderFactory()}>
	  <Row className="mb-4 p-2">
	    <Col xs={12} lg={4} className="d-flex flex-col justify-content-end align-items-end" />
	    <Col xs={2} mb={1} lg={1} className="d-flex flex-col justify-content-lg-center align-items-center justify-content-sm-start mb-2 mb-sm-0"/>
	    <Col xs={2} mb={1} lg={1} className="d-flex flex-col justify-content-lg-center align-items-center justify-content-sm-start mb-2 mb-sm-0"/>
	  </Row>
	  <Table>
	    <TableHeader />
	    <TableBody />
	  </Table>
	</DatatableWrapper>
      </div>
      </>
    );
  }
}
