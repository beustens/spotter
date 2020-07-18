window.post = function(url, data) {
    return fetch(url, {method: "POST", body: JSON.stringify(data)});
}


function enterParam(paramElement) {
    // entering values via input elements
    let paramKey = paramElement.name;
    let paramVal = paramElement.value;
    
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
    const picker = document.getElementById("picker");
    if ("pickersize" in data) {
        // in preview state, display picker and set size
        const size = data.pickersize;
        picker.style.width = size.width+"%";
        picker.style.height = size.height+"%";
        picker.style.display = "block";
    } else {
        // hide picker
        picker.style.display = "none";
    }

    // configure mirror
    const mirror = document.getElementById("mirror");
    if ("mirrorsize" in data) {
        // display mirror and set coords/size
        const size = data.mirrorsize;
        mirror.style.width = size.width+"%";
        mirror.style.height = size.height+"%";
        mirror.style.top = size.top+"%";
        mirror.style.left = size.left+"%";
        mirror.style.display = "block";
    } else {
        // hide mirror
        mirror.style.display = "none";
    }
};

const settingsSource = new EventSource("/settings");
settingsSource.onmessage = function(event) {
    const data = JSON.parse(event.data); // parse dictionary
    // insert parameters in inputs
    for (const element of document.getElementsByTagName("input")) {
        if (element.name in data) {
            element.value = data[element.name];
        }
    }
}

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