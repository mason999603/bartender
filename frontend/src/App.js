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
import PhonePage from "@/pages/PhonePage";
import CollectionsPage from "@/pages/CollectionsPage";
import { ServiceModeProvider } from "@/context/ServiceModeContext";

function App() {
    return (
        <div className="App">
            <ServiceModeProvider>
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
                            <Route path="/collections" element={<CollectionsPage />} />
                            <Route path="/phone" element={<PhonePage />} />
                        </Routes>
                    </main>
                </BrowserRouter>
            </ServiceModeProvider>
        </div>
    );
}

export default App;
