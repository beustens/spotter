window.post = function(url, data) {
    return fetch(url, {method: "POST", body: JSON.stringify(data)});
}


function fillTargetList() {
    fetch("targets.json")
        .then(res => res.json())
        .then(data => {
            const targetsEle = document.getElementById("targets");
            for (const name of Object.keys(data)) {
                // create option for target
                const targetEle = document.createElement("option");
                targetEle.innerHTML = name;
                targetEle.value = name;
                // add to list
                targetsEle.appendChild(targetEle);
            }
        })
}

fillTargetList();


function enterParam(paramElement) {
    // entering values via input elements
    let paramKey = paramElement.name;
    let paramVal = ((paramElement.type == "checkbox") ? paramElement.checked : paramElement.value);
    
    // send to server
    post("/setting", {param: paramKey, value: paramVal});
}


// listen to server side event (server updates un-requested)
const changeSource = new EventSource("/change");
changeSource.onmessage = function(event) {
    const data = JSON.parse(event.data); // parse dictionary
    parseSettings(data.settings);
    parseUpdate(data.update);
    parseState(data.state);
    parseRings(data.rings);
    parseMarks(data.marks);
    parseMarkSize(data.marksize);
}


function parseSettings(data) {
    if (data == undefined) return;

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

    // insert parameters in dropdown menu
    for (const selectEle of document.getElementsByTagName("select")) {
        if (selectEle.name in data) {
            selectEle.value = data[selectEle.name];
        }
    }
}


function parseUpdate(data) {
    if (data == undefined) return;

    // display debug infos
    const infosEle = document.getElementById("infos");
    infosEle.innerHTML = "";
    for (const [key, val] of Object.entries(data.infos)) {
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

    // display progress
    const progressEle = document.getElementById("progress");
    if ("progress" in data) {
        progressEle.style.width = data.progress+"%";
        progressEle.parentElement.style.display = "block";
    } else {
        progressEle.parentElement.style.display = "none";
    }
}


function parseState(data) {
    if (data == undefined) return;

    // configure mirror picker overlay
    const pickerEle = document.getElementById("picker");
    const size = data.pickersize;
    if (size != undefined) {
        // in preview state, display picker and set size
        pickerEle.style.width = size.width+"%";
        pickerEle.style.height = size.height+"%";
        pickerEle.style.display = "block";
    } else {
        // hide picker
        pickerEle.style.display = "none";
    }

    // configure message
    const msgEle = document.getElementById("message");
    if (data.state == "COLLECT") {
        msgEle.style.display = "block";
    } else {
        msgEle.style.display = "none";
    }

    // show or hide state specific settings
    // discipline in preview state
    const disciplineEle = document.getElementById("discipline");
    if (data.state == "PREVIEW") {
        disciplineEle.style.display = "block";
    } else {
        disciplineEle.style.display = "none";
    }
    // ring corrections in detect state
    const ringcorrEle = document.getElementById("ringcorrections");
    if (data.state == "DETECT") {
        ringcorrEle.style.display = "block";
    } else {
        ringcorrEle.style.display = "none";
    }
}


function parseRings(data) {
    // configure rings
    if (data == undefined) return;

    const ringsEle = document.getElementById("rings");
    ringsEle.innerHTML = "";
    
    // insert marks in container
    for (const size of data) {
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


let selectedMark = null;

function parseMarks(data) {
    // configure marks
    if (data == undefined) return;

    // overlay container
    const marksEle = document.getElementById("marks");
    marksEle.innerHTML = "";

    // list container
    const listEle = document.getElementById("marklist");
    listEle.innerHTML = "";

    document.getElementById("markselect").style.display = "none";
    selectedMark = null;
    let ringSum = 0;
    let innerSum = 0;
    // insert marks in container in reverse order to have newest at top
    for (let iMark = data.length-1; iMark >= 0; iMark--) {
        const mark = data[iMark];

        // count limited values and innermost rings
        const limValue = Math.min(mark.ring, 10);
        ringSum += limValue;
        if (mark.ring > 10) innerSum += 1;

        // create overlay mark element
        const markEle = document.createElement("div");
        markEle.classList.add("overlay");
        markEle.classList.add("circle");
        markEle.classList.add("mark");
        const pos = mark.relpos;
        markEle.style.top = pos.top+"%";
        markEle.style.left = pos.left+"%";
        // add mark to overlay container
        marksEle.appendChild(markEle);

        // create list mark element
        const entryEle = document.createElement("div");
        entryEle.classList.add("bar");
        entryEle.style.width = 10*limValue+"%";
        entryEle.innerHTML = limValue;
        if (mark.ring > 10) entryEle.innerHTML += "+";
        // add entry to list container
        listEle.appendChild(entryEle);

        // add listener for selection
        markEle.addEventListener("click", function(){
            selectMark(iMark, mark.pixpos);
            highlightSelection(markEle);
            highlightSelection(entryEle);
        });
        entryEle.addEventListener("click", function(){
            selectMark(iMark, mark.pixpos);
            highlightSelection(markEle);
            highlightSelection(entryEle);
        });
    }

    // show sum
    const ringSumEle = document.getElementById("ringsum");
    ringSumEle.innerHTML = ringSum;
    if (innerSum > 0) ringSumEle.innerHTML += (" (+"+innerSum+")");
}


function parseMarkSize(data) {
    if (data == undefined) return;

    // configure mark overlay size
    for (const markEle of document.getElementsByClassName("mark")) {
        markEle.style.width = data.width+"%";
        markEle.style.height = data.height+"%";
    }
}


function selectMark(markIndex, markPos) {
    // show selection
    document.getElementById("markselect").style.display = "block";
    // insert current position in input elements for change
    document.getElementById("markleft").value = markPos.left;
    document.getElementById("marktop").value = markPos.top;
    // update object for selected mark
    selectedMark = {
        index: markIndex, 
        pos: markPos
    }
}


function highlightSelection(ele) {
    // clear old highlights
    for (const childEle of ele.parentElement.children) {
        childEle.classList.remove("selected");
    }
    // highlight
    ele.classList.add("selected");
}


function correctMark() {
    // get correction coordinates by user
    const left = document.getElementById("markleft").value;
    const top = document.getElementById("marktop").value;

    // send to server
    post("/mark", {
        action: "correct", 
        index: selectedMark.index, 
        pos: {left: left, top: top}
    });
}


function copyMark() {
    post("/mark", {action: "copy", index: selectedMark.index});
}


function deleteMark() {
    post("/mark", {action: "delete", index: selectedMark.index});
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
