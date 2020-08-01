window.post = function(url, data) {
    return fetch(url, {method: "POST", body: JSON.stringify(data)});
}


function enterParam(paramElement) {
    // entering values via input elements
    let paramKey = paramElement.name;
    let paramVal = (paramElement.type == "checkbox" ? paramElement.checked : paramElement.value);
    
    // send to server
    post("/setting", {param: paramKey, value: paramVal});
}


// listen to server side event (server updates un-requested)
const infoSource = new EventSource("/infos");
infoSource.onmessage = function(event) {
    const data = JSON.parse(event.data); // parse dictionary
    
    // display debug infos
    const infosEle = document.getElementById("infos");
    infosEle.innerHTML = "";
    for (const [key, val] of Object.entries(data)) {
        // create info element
        const infoEle = document.createElement("div");
        // add key
        infoEle.innerHTML = key;
        // add value
        const valEle = document.createElement("span");
        valEle.innerHTML = val;
        valEle.classList.add("statevar");
        infoEle.appendChild(valEle);
        // add info element to infos element
        infosEle.appendChild(infoEle);
    }
};

const stateSource = new EventSource("/state");
stateSource.onmessage = function(event) {
    const data = JSON.parse(event.data); // parse dictionary

    // configure mirror picker overlay
    const pickerEle = document.getElementById("picker");
    if ("pickersize" in data) {
        // in preview state, display picker and set size
        const size = data.pickersize;
        pickerEle.style.width = size.width+"%";
        pickerEle.style.height = size.height+"%";
        pickerEle.style.display = "block";
    } else {
        // hide picker
        pickerEle.style.display = "none";
    }

    // configure message
    const msgEle = document.getElementById("message");
    if (data.state === "COLLECT") {
        msgEle.style.display = "block";
    } else {
        msgEle.style.display = "none";
    }
};

const settingsSource = new EventSource("/settings");
settingsSource.onmessage = function(event) {
    const data = JSON.parse(event.data); // parse dictionary
    // insert parameters in inputs
    for (const inputEle of document.getElementsByTagName("input")) {
        if (inputEle.name in data) {
            if (inputEle.type == "checkbox") {
                inputEle.checked = data[inputEle.name];
            } else {
                inputEle.value = data[inputEle.name];
            }
        }
    }
}

const ringsSource = new EventSource("/rings");
ringsSource.onmessage = function(event) {
    const data = JSON.parse(event.data); // parse dictionary

    // configure rings
    const ringsEle = document.getElementById("rings");
    ringsEle.innerHTML = "";
    // insert marks in container
    if ("ringsizes" in data) {
        for (const size of data.ringsizes) {
            // create ring element
            const ringEle = document.createElement("div");
            ringEle.classList.add("overlay");
            ringEle.classList.add("circle");
            ringEle.style.width = size.width+"%";
            ringEle.style.height = size.height+"%";
            ringEle.style.top = size.top+"%";
            ringEle.style.left = size.left+"%";
            ringEle.style.pointerEvents = "none"; // do not block mouse clicks
            // add ring to container
            ringsEle.appendChild(ringEle);
        }
    }
};

const marksSource = new EventSource("/marks");
marksSource.onmessage = function(event) {
    const data = JSON.parse(event.data); // parse dictionary
    
    const marksEle = document.getElementById("marks");
    marksEle.innerHTML = "";
    // insert marks in container
    for (const mark of data) {
        // create mark element
        const markEle = document.createElement("div");
        markEle.classList.add("overlay");
        markEle.classList.add("circle");
        markEle.classList.add("mark");
        markEle.style.top = mark.top+"%";
        markEle.style.left = mark.left+"%";
        // add mark to container
        marksEle.appendChild(markEle);
    }
}


function toggleMode(btnElement) {
    // start or stop detecting
    if (btnElement.value === "Start") {
        // starting
        post("/setting", {param: "mode", value: "start"});
        btnElement.value = "Stop"
    } else {
        // stopping
        post("/setting", {param: "mode", value: "preview"});
        btnElement.value = "Start"
    }
}
