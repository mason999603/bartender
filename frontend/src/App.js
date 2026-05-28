import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Topbar from "@/components/Topbar";
import ChatPage from "@/pages/ChatPage";
import CocktailsPage from "@/pages/CocktailsPage";
import ToolsPage from "@/pages/ToolsPage";
import RegularsPage from "@/pages/RegularsPage";
import MemoryPage from "@/pages/MemoryPage";
import InventoryPage from "@/pages/InventoryPage";

function App() {
    return (
        <div className="App">
            <BrowserRouter>
                <Topbar />
                <main>
                    <Routes>
                        <Route path="/" element={<ChatPage />} />
                        <Route path="/cocktails" element={<CocktailsPage />} />
                        <Route path="/tools" element={<ToolsPage />} />
                        <Route path="/inventory" element={<InventoryPage />} />
                        <Route path="/regulars" element={<RegularsPage />} />
                        <Route path="/memory" element={<MemoryPage />} />
                    </Routes>
                </main>
            </BrowserRouter>
        </div>
    );
}

export default App;
