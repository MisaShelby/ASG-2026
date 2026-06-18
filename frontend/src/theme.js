import { createTheme } from "@mui/material/styles";

// Thème commun ASG-2026 (tonalité "laboratoire/bio")
const theme = createTheme({
    palette: {
        mode: "light",
        primary: { main: "#1565c0" },
        secondary: { main: "#2e7d32" },
        background: { default: "#f4f6f8" },
    },
    shape: { borderRadius: 10 },
    typography: {
        h4: { fontWeight: 700 },
        h6: { fontWeight: 600 },
    },
});

export default theme;
