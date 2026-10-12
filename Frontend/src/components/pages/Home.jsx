import React from 'react';

const Header = () => {
  const headerStyle = {
    background: '#333',
    color: '#fff',
    padding: '1em',
    textAlign: 'center',
  };

  return (
    <div style={headerStyle}>
      <h2>Banking App</h2>
    </div>
  );
};

const MovingCard = () => {
  const cardStyle = {
    background: '#f0f0f0',
    margin: '1em',
    padding: '1em',
    borderRadius: '8px',
    boxShadow: '0 4px 8px rgba(0, 0, 0, 0.1)',
    transition: 'transform 0.3s ease-in-out',
    cursor: 'pointer',
  };

  const handleCardClick = () => {
    // Add functionality for card click
    console.log('Card clicked!');
  };

  return (
    <div style={cardStyle} onClick={handleCardClick}>
      <h3>Card Title</h3>
      <p>Card Content</p>
    </div>
  );
};

export const Home = () => {
  const containerStyle = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
  };

  const titleStyle = {
    fontSize: '2em',
  };

  const cardContainerStyle = {
    display: 'flex',
    justifyContent: 'center',
  };

  return (
    <div>
      {/* <Header /> */}
      <div style={containerStyle}>
        <h1 style={titleStyle}>Welcome to Our Banking App</h1>
        <div style={cardContainerStyle}>
          <MovingCard />
          <MovingCard />
          {/* Add more MovingCard components as needed */}
        </div>
        {/* Add other content here */}
      </div>
    </div>
  );
};
