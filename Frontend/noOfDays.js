function noOfDaysCalculation(startDate) {
 
    // console.log("start date " + startDate);
    
    const currentDate = new Date();
    const inputDate = new Date(currentDate);
  
    // Format the date in the desired format
    const outputDateString = inputDate.toISOString();
    var outputDateString1 = "2020-02-01T16:19:03.785Z";
    const startDateString = startDate;
    const endDateString = outputDateString;
  
    // Create Date objects from the input strings
    const startDate1 = new Date(startDateString);
    const endDate = new Date(endDateString);
  
    startDate1.setHours(0, 0, 0, 0);
    endDate.setHours(0, 0, 0, 0);
  
    const timeDifference = Math.abs(endDate - startDate1);
    const daysDifference = Math.floor(timeDifference / (1000 * 60 * 60 * 24));
    return daysDifference;
  }
  module.exports={
    noOfDaysCalculation
  }