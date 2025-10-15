import "bootstrap/dist/css/bootstrap.css";
import { Col, Row, Table } from "react-bootstrap";
import {
  DatatableWrapper,
  Filter,
  Pagination,
  PaginationOptions,
  TableBody,
  TableColumnType,
  TableHeader
} from "react-bs-datatable";

import axios from 'axios';
import React from "react";
import ModalImage from "react-modal-image";
import {ModalRequestSwap, ModalParty} from "./modals.js";

function SwapStatus({enabled}) {
  if (!enabled) {
    return (
      <span className="justify-content-md-center">
	Room swaps have been disabled for the remainder of the event.
      </span>
    );
  }
}

export default class RoomDataTable extends React.Component {
  state = {
    rooms : [],
    jwt: "",
    sortColumn: "number", // default column to sort by
    sortDirection: "asc", // default sort direction,
    swaps_enabled: true,
    guest_hotels: [],
    refreshTimer: null
  }

  // utility function for sorting table room # strings as numbers
  sortData = () => {
    this.setState((prevState) => {
      const sortedRooms = [...prevState.rooms];
      sortedRooms.sort((a, b) => {
        const valA = a[prevState.sortColumn];
        const valB = b[prevState.sortColumn];
        if (prevState.sortDirection === "asc") {
          return valA - valB; // for numerical values
        } else {
          return valB - valA; // for descending order
        }
      });
      return { rooms: sortedRooms };
    });
  };

  storyHeaderFactory(swaps_enabled, guest_hotels) {
    var roomTable = [
      {
        prop: "number",
        title: "Number",
        isSortable: true,
        isFilterable: true
      },
      {
        prop: "name_take3",
        title: "Type",
        isFilterable: true
      },
      {
        prop: "floorplan",
        title: "FloorPlan",
        cell: (row) => (
	  row.floorplans && (
            <ModalImage
              small={"layouts/" + row.floorplans[1]}
              large={"layouts/" + row.floorplans[0]}
              alt="Hotel Floor Plan"
            />
	  )
        )
      },
      {
        prop: "button",
        cell: (row) => (
	  <>
            <ModalRequestSwap row={row} swaps_enabled={swaps_enabled} />
	    {row.is_party ? <ModalParty room_number={row.number} /> : ""}
	  </>
        )
      }
    ];
    if (guest_hotels && guest_hotels.length > 1) {
      roomTable.unshift({
        prop: "name_hotel",
        title: "Hotel",
        isSortable: true,
        isFilterable: true
      });
    }

    let STORY_HEADERS: TableColumnType<ArrayElementType>[] = roomTable;
    // handle column header clicks
    STORY_HEADERS[0].onHeaderClick = () => {
      this.setState(
        (prevState) => ({
          sortColumn: "number",
          sortDirection: prevState.sortColumn === "number" && prevState.sortDirection === "asc" ? "desc" : "asc",
        }),
        this.sortData // callback to sort data after state is updated
      );
    };
    return STORY_HEADERS;					
  };

  loadRooms() {
    const jwt = JSON.parse(localStorage.getItem('jwt'));
    if ( jwt == null ) {
      this.setState({error: 'auth'});
      return;
    }
    axios.post(window.location.protocol + "//" + window.location.hostname + ":" + (window.location.protocol == "https:" ? "8443" : "8000") +  "/api/rooms/", {
            jwt: jwt["jwt"]
      })
      .then(res => {
        console.log(res.data);
        const data = res.data;

        // Convert room number strings to integers
        const roomsWithIntegers = data.rooms.map(room => ({
          ...room,
          number: parseInt(room.number, 10)
        }));
        this.setState({
          rooms: roomsWithIntegers,
          swaps_enabled: data.swaps_enabled,
	  guest_hotels: data.guest_hotels
        }, this.sortData0);
      })
      .catch((error) => {
        this.setState({errorMessage: error.message});
        if (error.response) {
          if (error.response.status === 401) {
            this.setState({ error: 'auth' });
          } else if (error.request) {
            console.log("network error");
          } else {
            console.log("unhandled error " + error.response.status + ", " + error.response.data);
          }
	}
      });
    this.sortData();
  }
					
  componentDidMount() {
    this.loadRooms();
  }					

  render(){
    let {error} = this.state;
    return(
      <div>
      <SwapStatus enabled={this.state.swaps_enabled} />
      <DatatableWrapper
        body={this.state.rooms}
        headers={this.storyHeaderFactory(this.state.swaps_enabled, this.state.guest_hotels)}
        paginationOptionsProps={{
          initialState: {
            rowsPerPage: 10,
            options: [5, 10, 15, 20]
          }
        }}
      >
        <Row className="mb-4 p-2">
          <Col
            xs={12}
            lg={4}
            className="d-flex flex-col justify-content-end align-items-end"
          >
            <Filter />
          </Col>
          <Col
            xs={12}
            sm={6}
            lg={4}
            className="d-flex flex-col justify-content-lg-center align-items-center justify-content-sm-start mb-2 mb-sm-0"
          >
            <PaginationOptions />
          </Col>
          <Col
            xs={12}
            sm={6}
            lg={4}
            className="d-flex flex-col justify-content-end align-items-end"
          >
            <Pagination />
          </Col>
        </Row>
        <Table>
          <TableHeader />
          <TableBody />
        </Table>
      </DatatableWrapper>
      </div>
    )
  }
}
