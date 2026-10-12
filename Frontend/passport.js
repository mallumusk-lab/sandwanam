const GoogleStrategy = require("passport-google-oauth20").Strategy;
const passport = require("passport");

passport.use(
	new GoogleStrategy(
		{
			clientID: process.env.CLIENT_ID,
			clientSecret: process.env.CLIENT_SECRET,
			callbackURL: "http://43.204.202.44:4000/auth/google/callback.com",
			scope: ["profile", "email"],
		},
		function (accessToken, refreshToken, profile, callback) {
			console.log('Profile Data')
			console.log(profile)
			callback(null, profile);
		}
	)
);

passport.serializeUser((user, done) => {
	done(null, user);
});

passport.deserializeUser((user, done) => {
	done(null, user);
});
